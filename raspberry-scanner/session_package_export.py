"""Export a finished Raspberry capture session to DINAMIC_LOCAL_AISLE_EXPORT v2 ZIP."""

from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from capture_session_store import CaptureSessionState, CaptureSessionStore, PhotoCaptureRecord
from local_csv_rows import LocalCsvBuildResult, build_local_csv_rows
from local_package_contract import (
    CHECKSUM_ALGORITHM,
    LOCAL_CSV_SCHEMA_VERSION,
    PACKAGE_KIND,
    PACKAGE_VERSION,
)


class SessionPackageExportError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ResolvedPhotoAsset:
    record: PhotoCaptureRecord
    content: bytes
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class SessionPackageExportResult:
    export_id: str
    zip_path: Path
    capture_session_id: str
    package_checksum_sha256: str
    csv_checksum_sha256: str


@dataclass(frozen=True)
class SessionPackageExportContext:
    inventory_id: str
    aisle_id: str
    device_id: str


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_photo_descriptor_line(
    *,
    capture_photo_id: str,
    sequence_number: int,
    file_name: str,
    mime_type: str,
    size_bytes: int,
    sha256: str,
    asset_variant: str,
) -> str:
    return ":".join(
        [
            capture_photo_id,
            str(sequence_number),
            file_name,
            mime_type,
            str(size_bytes),
            sha256,
            asset_variant,
        ]
    )


def build_package_content_fingerprint(
    *,
    csv_checksum_sha256: str,
    photos: list[ResolvedPhotoAsset],
    freeze_id: str | None = None,
    freeze_generation: int | None = None,
) -> str:
    sorted_photos = sorted(
        photos,
        key=lambda p: (p.record.sequence_number, p.record.capture_photo_id),
    )
    photo_part = "|".join(
        _canonical_photo_descriptor_line(
            capture_photo_id=photo.record.capture_photo_id,
            sequence_number=photo.record.sequence_number,
            file_name=photo.record.file_name or "",
            mime_type="image/jpeg",
            size_bytes=photo.size_bytes,
            sha256=photo.sha256,
            asset_variant="ORIGINAL",
        )
        for photo in sorted_photos
    )
    payload = "|".join(
        [
            f"pkg-v{PACKAGE_VERSION}",
            freeze_id or "",
            str(freeze_generation or ""),
            csv_checksum_sha256,
            photo_part,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_ids(inventory_id: str, aisle_id: str) -> None:
    if not inventory_id.strip():
        raise SessionPackageExportError(
            "EXPORT_INVENTORY_ID_REQUIRED",
            "inventory_id is required",
        )
    if not aisle_id.strip():
        raise SessionPackageExportError(
            "EXPORT_AISLE_ID_REQUIRED",
            "aisle_id is required",
        )


def _load_finished_session(
    store: CaptureSessionStore,
    capture_session_id: str,
) -> CaptureSessionState:
    session = store.load_session(capture_session_id)
    if session is None:
        raise SessionPackageExportError(
            "EXPORT_SESSION_NOT_FOUND",
            f"session not found: {capture_session_id}",
        )
    if session.state != "FINISHED":
        raise SessionPackageExportError(
            "EXPORT_SESSION_NOT_FINISHED",
            f"session state must be FINISHED, got {session.state}",
        )
    return session


def _select_complete_photos(session: CaptureSessionState) -> list[PhotoCaptureRecord]:
    if any(photo.status == "CAPTURING" for photo in session.photos):
        raise SessionPackageExportError(
            "EXPORT_PHOTOS_NOT_TERMINAL",
            "session still has CAPTURING photos",
        )
    complete = [photo for photo in session.photos if photo.status == "COMPLETE"]
    capture_ids = [photo.capture_photo_id for photo in complete]
    if len(capture_ids) != len(set(capture_ids)):
        raise SessionPackageExportError(
            "EXPORT_DUPLICATE_CAPTURE_PHOTO_ID",
            "duplicate capture_photo_id in session",
        )
    sequences = [photo.sequence_number for photo in complete]
    if len(sequences) != len(set(sequences)):
        raise SessionPackageExportError(
            "EXPORT_DUPLICATE_SEQUENCE_NUMBER",
            "duplicate sequence_number in session",
        )
    return sorted(complete, key=lambda p: p.sequence_number)


def _resolve_photo_assets(
    session: CaptureSessionState,
    photos_root: Path,
    complete_photos: list[PhotoCaptureRecord],
) -> list[ResolvedPhotoAsset]:
    session_dir = photos_root / session.capture_session_id
    resolved: list[ResolvedPhotoAsset] = []
    for photo in complete_photos:
        if not photo.file_name:
            raise SessionPackageExportError(
                "EXPORT_PHOTO_FILE_NAME_MISSING",
                f"photo {photo.capture_photo_id} missing file_name",
            )
        final_path = (session_dir / photo.file_name).resolve()
        if not final_path.is_file():
            raise SessionPackageExportError(
                "EXPORT_PHOTO_FILE_MISSING",
                f"photo file missing: {photo.file_name}",
            )
        if session_dir.resolve() not in final_path.parents:
            raise SessionPackageExportError(
                "EXPORT_PHOTO_PATH_INVALID",
                f"photo path escapes session directory: {photo.file_name}",
            )
        content = final_path.read_bytes()
        actual_sha = _sha256_bytes(content)
        if photo.photo_sha256 and photo.photo_sha256.lower() != actual_sha:
            raise SessionPackageExportError(
                "EXPORT_PHOTO_SHA_MISMATCH",
                f"stored sha256 mismatch for {photo.file_name}",
            )
        if photo.photo_size_bytes is not None and photo.photo_size_bytes != len(content):
            raise SessionPackageExportError(
                "EXPORT_PHOTO_SIZE_MISMATCH",
                f"stored size mismatch for {photo.file_name}",
            )
        resolved.append(
            ResolvedPhotoAsset(
                record=photo,
                content=content,
                sha256=actual_sha,
                size_bytes=len(content),
            )
        )
    return resolved


def _build_manifest(
    *,
    csv_build: LocalCsvBuildResult,
    session: CaptureSessionState,
    context: SessionPackageExportContext,
    photos: list[ResolvedPhotoAsset],
    package_checksum_sha256: str,
) -> dict[str, object]:
    photo_entries: list[dict[str, object]] = []
    for asset in photos:
        photo = asset.record
        assert photo.file_name is not None
        photo_entries.append(
            {
                "capture_photo_id": photo.capture_photo_id,
                "client_file_id": photo.capture_photo_id,
                "sequence_number": photo.sequence_number,
                "file_name": photo.file_name,
                "mime_type": "image/jpeg",
                "size_bytes": asset.size_bytes,
                "sha256": asset.sha256,
                "width": None,
                "height": None,
                "asset_variant": "ORIGINAL",
            }
        )
    included = len(photo_entries)
    return {
        "schema_version": LOCAL_CSV_SCHEMA_VERSION,
        "package_kind": PACKAGE_KIND,
        "package_version": PACKAGE_VERSION,
        "status": "COMPLETE",
        "export_id": csv_build.export_id,
        "exported_at": csv_build.exported_at,
        "inventory_id": context.inventory_id,
        "aisle_id": context.aisle_id,
        "capture_session_id": session.capture_session_id,
        "freeze_id": None,
        "freeze_generation": None,
        "row_count": csv_build.row_count,
        "expected_photo_count": included,
        "included_photo_count": included,
        "missing_photos": [],
        "csv_checksum_sha256": csv_build.csv_checksum_sha256,
        "checksum_sha256": csv_build.csv_checksum_sha256,
        "checksum_algorithm": CHECKSUM_ALGORITHM,
        "package_checksum_sha256": package_checksum_sha256,
        "summary": {
            "photo_count": included,
            "position_event_count": csv_build.position_event_count,
            "product_result_count": csv_build.product_result_count,
            "rejected_detection_count": csv_build.rejected_detection_count,
        },
        "photos": photo_entries,
    }


def _validate_csv_manifest_consistency(
    csv_build: LocalCsvBuildResult,
    photos: list[ResolvedPhotoAsset],
) -> None:
    photo_ids = {asset.record.capture_photo_id for asset in photos}
    for row in csv_build.rows:
        capture_photo_id = row["capture_photo_id"]
        if capture_photo_id and capture_photo_id not in photo_ids:
            raise SessionPackageExportError(
                "EXPORT_CSV_PHOTO_UNDECLARED",
                f"CSV references undeclared photo {capture_photo_id}",
            )


def _build_zip_bytes(
    csv_text: str,
    manifest: dict[str, object],
    photos: list[ResolvedPhotoAsset],
) -> bytes:
    csv_bytes = csv_text.encode("utf-8")
    manifest_bytes = f"{json.dumps(manifest, indent=2, sort_keys=True)}\n".encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("results.csv", csv_bytes)
        zf.writestr("manifest.json", manifest_bytes)
        for asset in photos:
            assert asset.record.file_name is not None
            zf.writestr(f"photos/{asset.record.file_name}", asset.content)
    return buf.getvalue()


def export_finished_session_package(
    *,
    session_store: CaptureSessionStore,
    photos_root: Path,
    output_directory: Path,
    capture_session_id: str,
    context: SessionPackageExportContext,
    export_id: str | None = None,
) -> SessionPackageExportResult:
    _validate_ids(context.inventory_id, context.aisle_id)
    session = _load_finished_session(session_store, capture_session_id)
    complete_photos = _select_complete_photos(session)
    if not complete_photos:
        raise SessionPackageExportError(
            "EXPORT_NO_COMPLETE_PHOTOS",
            "session has no COMPLETE photos to export",
        )
    photo_assets = _resolve_photo_assets(session, photos_root, complete_photos)
    try:
        csv_build = build_local_csv_rows(
            session,
            complete_photos=complete_photos,
            inventory_id=context.inventory_id,
            aisle_id=context.aisle_id,
            device_id=context.device_id,
            export_id=export_id,
        )
    except ValueError as exc:
        raise SessionPackageExportError("EXPORT_CSV_BUILD_FAILED", str(exc)) from exc
    _validate_csv_manifest_consistency(csv_build, photo_assets)
    package_checksum = build_package_content_fingerprint(
        csv_checksum_sha256=csv_build.csv_checksum_sha256,
        photos=photo_assets,
    )
    manifest = _build_manifest(
        csv_build=csv_build,
        session=session,
        context=context,
        photos=photo_assets,
        package_checksum_sha256=package_checksum,
    )
    zip_bytes = _build_zip_bytes(csv_build.csv_text, manifest, photo_assets)

    from src.application.services.local_inventory_package_parser import (
        parse_local_inventory_package,
    )

    try:
        parse_local_inventory_package(zip_bytes)
    except Exception as exc:
        raise SessionPackageExportError(
            "EXPORT_PACKAGE_PARSE_FAILED",
            f"backend parser rejected package: {exc}",
        ) from exc

    output_directory.mkdir(parents=True, exist_ok=True)
    final_name = f"{session.aisle_code}_{csv_build.export_id}.zip"
    final_path = output_directory / final_name
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{final_name}.",
        dir=output_directory,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(zip_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, final_path)
    except OSError:
        _safe_unlink(temp_path)
        raise

    return SessionPackageExportResult(
        export_id=csv_build.export_id,
        zip_path=final_path,
        capture_session_id=session.capture_session_id,
        package_checksum_sha256=package_checksum,
        csv_checksum_sha256=csv_build.csv_checksum_sha256,
    )


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
