"""Parse and validate DINAMIC_LOCAL_AISLE_EXPORT ZIP packages (stdlib zipfile)."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from typing import Any

PACKAGE_KIND = "DINAMIC_LOCAL_AISLE_EXPORT"
SUPPORTED_PACKAGE_VERSIONS = frozenset({1, 2})
MAX_ZIP_ENTRIES = 5000
MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_SINGLE_FILE_BYTES = 80 * 1024 * 1024
REQUIRED_ROOT_FILES = frozenset({"results.csv", "manifest.json"})

class LocalInventoryPackageError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class PackagePhotoBytes:
    capture_photo_id: str
    client_file_id: str
    sequence_number: int | None
    file_name: str
    mime_type: str
    size_bytes: int
    sha256: str
    width: int | None
    height: int | None
    asset_variant: str
    content: bytes


@dataclass(frozen=True)
class ParsedLocalInventoryPackage:
    package_kind: str
    package_version: int
    status: str
    export_id: str
    inventory_id: str
    aisle_id: str | None
    capture_session_id: str | None
    freeze_id: str | None
    csv_bytes: bytes
    csv_checksum_sha256: str
    package_checksum_sha256: str | None
    manifest: dict[str, Any]
    photos: tuple[PackagePhotoBytes, ...]
    expected_photo_count: int
    included_photo_count: int


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _manifest_field_str(manifest: dict[str, Any], key: str) -> str:
    return str(manifest.get(key) or "").strip()


def _read_csv_envelope(csv_bytes: bytes) -> tuple[frozenset[str], dict[str, str] | None]:
    """Return CSV headers and first data row, or ``None`` when the file is header-only."""
    try:
        text = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise LocalInventoryPackageError(
            "PACKAGE_CSV_INVALID_ENCODING",
            "results.csv must be UTF-8",
        ) from exc
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        fieldnames = reader.fieldnames or ()
        headers = frozenset(str(name) for name in fieldnames if name)
        raw = next(reader, None)
    except csv.Error as exc:
        raise LocalInventoryPackageError(
            "PACKAGE_CSV_MALFORMED",
            f"results.csv is not valid RFC 4180 CSV: {exc}",
        ) from exc
    if raw is None:
        return headers, None
    row: dict[str, str] = {}
    for key, value in raw.items():
        if key is None:
            continue
        row[str(key)] = (value or "").strip() if value is not None else ""
    return headers, row


def _resolve_envelope_field(
    key: str,
    *,
    headers: frozenset[str],
    row: dict[str, str] | None,
    manifest: dict[str, Any],
    required: bool,
) -> str:
    manifest_val = _manifest_field_str(manifest, key)
    if key in headers and row is not None:
        csv_val = row.get(key, "")
        if manifest_val and manifest_val != csv_val:
            raise LocalInventoryPackageError(
                "PACKAGE_ENVELOPE_MISMATCH",
                f"{key} in manifest does not match results.csv",
            )
        canonical = csv_val
    else:
        canonical = manifest_val
    if required and not canonical:
        raise LocalInventoryPackageError(
            "PACKAGE_MANIFEST_INVALID",
            f"package requires {key} (results.csv column or manifest)",
        )
    return canonical


@dataclass(frozen=True)
class _ResolvedPackageEnvelope:
    export_id: str
    inventory_id: str
    aisle_id: str | None
    capture_session_id: str | None
    freeze_id: str | None


def _resolve_package_envelope(
    manifest: dict[str, Any],
    csv_bytes: bytes,
) -> _ResolvedPackageEnvelope:
    headers, row = _read_csv_envelope(csv_bytes)
    export_id = _resolve_envelope_field(
        "export_id", headers=headers, row=row, manifest=manifest, required=True
    )
    inventory_id = _resolve_envelope_field(
        "inventory_id", headers=headers, row=row, manifest=manifest, required=True
    )
    aisle_id = _resolve_envelope_field(
        "aisle_id", headers=headers, row=row, manifest=manifest, required=False
    )
    capture_session_id = _resolve_envelope_field(
        "capture_session_id",
        headers=headers,
        row=row,
        manifest=manifest,
        required=False,
    )
    freeze_id = _resolve_envelope_field(
        "freeze_id", headers=headers, row=row, manifest=manifest, required=False
    )
    return _ResolvedPackageEnvelope(
        export_id=export_id,
        inventory_id=inventory_id,
        aisle_id=aisle_id or None,
        capture_session_id=capture_session_id or None,
        freeze_id=freeze_id or None,
    )


def _safe_member_name(name: str) -> str:
    normalized = name.replace("\\", "/").lstrip("/")
    if not normalized or normalized.endswith("/"):
        raise LocalInventoryPackageError(
            "PACKAGE_ZIP_INVALID_ENTRY",
            f"Invalid ZIP entry name: {name!r}",
        )
    parts = normalized.split("/")
    if any(p in {"", ".", ".."} for p in parts):
        raise LocalInventoryPackageError(
            "PACKAGE_ZIP_PATH_TRAVERSAL",
            f"Rejected ZIP entry path: {name!r}",
        )
    if normalized.startswith("__MACOSX/"):
        raise LocalInventoryPackageError(
            "PACKAGE_ZIP_INVALID_ENTRY",
            f"Rejected metadata entry: {name!r}",
        )
    return normalized


def _read_limited(zf: zipfile.ZipFile, info: zipfile.ZipInfo, *, limit: int) -> bytes:
    if info.file_size > limit:
        raise LocalInventoryPackageError(
            "PACKAGE_FILE_TOO_LARGE",
            f"ZIP entry {info.filename!r} exceeds {limit} bytes uncompressed",
        )
    with zf.open(info, "r") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise LocalInventoryPackageError(
            "PACKAGE_FILE_TOO_LARGE",
            f"ZIP entry {info.filename!r} exceeds {limit} bytes uncompressed",
        )
    return data


def parse_local_inventory_package(
    content: bytes,
    *,
    max_uncompressed_bytes: int = MAX_UNCOMPRESSED_BYTES,
) -> ParsedLocalInventoryPackage:
    if len(content) < 4 or content[:2] != b"PK":
        raise LocalInventoryPackageError(
            "PACKAGE_NOT_ZIP",
            "Payload is not a ZIP archive",
        )
    try:
        zf = zipfile.ZipFile(io.BytesIO(content), mode="r")
    except zipfile.BadZipFile as exc:
        raise LocalInventoryPackageError("PACKAGE_ZIP_CORRUPT", "ZIP archive is corrupt") from exc

    with zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        if len(infos) > MAX_ZIP_ENTRIES:
            raise LocalInventoryPackageError(
                "PACKAGE_TOO_MANY_ENTRIES",
                f"ZIP has more than {MAX_ZIP_ENTRIES} entries",
            )
        total_uncompressed = sum(int(i.file_size) for i in infos)
        if total_uncompressed > max_uncompressed_bytes:
            raise LocalInventoryPackageError(
                "PACKAGE_UNCOMPRESSED_TOO_LARGE",
                f"Uncompressed package exceeds {max_uncompressed_bytes} bytes",
            )

        by_name: dict[str, zipfile.ZipInfo] = {}
        for info in infos:
            name = _safe_member_name(info.filename)
            if name in by_name:
                raise LocalInventoryPackageError(
                    "PACKAGE_DUPLICATE_ENTRY",
                    f"Duplicate ZIP entry: {name}",
                )
            by_name[name] = info

        missing = REQUIRED_ROOT_FILES - set(by_name)
        if missing:
            raise LocalInventoryPackageError(
                "PACKAGE_MISSING_REQUIRED_FILE",
                f"ZIP missing required files: {', '.join(sorted(missing))}",
            )

        csv_bytes = _read_limited(zf, by_name["results.csv"], limit=MAX_SINGLE_FILE_BYTES)
        manifest_raw = _read_limited(zf, by_name["manifest.json"], limit=2 * 1024 * 1024)
        try:
            manifest = json.loads(manifest_raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LocalInventoryPackageError(
                "PACKAGE_MANIFEST_INVALID",
                "manifest.json is not valid UTF-8 JSON",
            ) from exc
        if not isinstance(manifest, dict):
            raise LocalInventoryPackageError(
                "PACKAGE_MANIFEST_INVALID",
                "manifest.json root must be an object",
            )

        package_kind = str(manifest.get("package_kind") or "")
        if package_kind != PACKAGE_KIND:
            raise LocalInventoryPackageError(
                "PACKAGE_KIND_UNSUPPORTED",
                f"Unsupported package_kind: {package_kind!r}",
            )
        try:
            package_version = int(manifest.get("package_version") or 0)
        except (TypeError, ValueError) as exc:
            raise LocalInventoryPackageError(
                "PACKAGE_VERSION_UNSUPPORTED",
                "package_version must be an integer",
            ) from exc
        if package_version not in SUPPORTED_PACKAGE_VERSIONS:
            raise LocalInventoryPackageError(
                "PACKAGE_VERSION_UNSUPPORTED",
                f"Unsupported package_version: {package_version}",
            )

        status = str(manifest.get("status") or "COMPLETE").upper()
        if status not in {"COMPLETE", "PARTIAL"}:
            raise LocalInventoryPackageError(
                "PACKAGE_STATUS_INVALID",
                f"Unsupported package status: {status}",
            )
        if status == "PARTIAL":
            raise LocalInventoryPackageError(
                "PACKAGE_PARTIAL_NOT_ACCEPTED",
                "PARTIAL packages are not accepted for import; re-export COMPLETE",
            )

        envelope = _resolve_package_envelope(manifest, csv_bytes)

        csv_checksum = str(
            manifest.get("csv_checksum_sha256") or manifest.get("checksum_sha256") or ""
        ).strip().lower()
        actual_csv_checksum = _sha256_hex(csv_bytes)
        if csv_checksum and csv_checksum != actual_csv_checksum:
            raise LocalInventoryPackageError(
                "PACKAGE_CSV_CHECKSUM_MISMATCH",
                "results.csv checksum does not match manifest",
            )

        photo_meta_list = manifest.get("photos")
        if not isinstance(photo_meta_list, list):
            raise LocalInventoryPackageError(
                "PACKAGE_MANIFEST_INVALID",
                "manifest.photos must be an array",
            )

        photos: list[PackagePhotoBytes] = []
        seen_ids: set[str] = set()
        for raw in photo_meta_list:
            if not isinstance(raw, dict):
                raise LocalInventoryPackageError(
                    "PACKAGE_MANIFEST_INVALID",
                    "manifest.photos entries must be objects",
                )
            capture_photo_id = str(raw.get("capture_photo_id") or "").strip()
            file_name = str(raw.get("file_name") or "").strip()
            if not capture_photo_id or not file_name:
                raise LocalInventoryPackageError(
                    "PACKAGE_MANIFEST_INVALID",
                    "photo entries require capture_photo_id and file_name",
                )
            if capture_photo_id in seen_ids:
                raise LocalInventoryPackageError(
                    "PACKAGE_DUPLICATE_PHOTO",
                    f"Duplicate capture_photo_id in manifest: {capture_photo_id}",
                )
            seen_ids.add(capture_photo_id)
            entry_name = _safe_member_name(f"photos/{file_name}")
            if entry_name not in by_name:
                raise LocalInventoryPackageError(
                    "PACKAGE_PHOTO_MISSING",
                    f"Photo listed in manifest missing from ZIP: {entry_name}",
                )
            content_bytes = _read_limited(
                zf, by_name[entry_name], limit=MAX_SINGLE_FILE_BYTES
            )
            actual_sha = _sha256_hex(content_bytes)
            declared_sha = str(raw.get("sha256") or "").strip().lower()
            if declared_sha and declared_sha != actual_sha:
                raise LocalInventoryPackageError(
                    "PACKAGE_PHOTO_CHECKSUM_MISMATCH",
                    f"Photo checksum mismatch for {file_name}",
                )
            declared_size = raw.get("size_bytes")
            if declared_size is not None and int(declared_size) != len(content_bytes):
                raise LocalInventoryPackageError(
                    "PACKAGE_PHOTO_SIZE_MISMATCH",
                    f"Photo size mismatch for {file_name}",
                )
            seq_raw = raw.get("sequence_number")
            sequence_number = int(seq_raw) if seq_raw is not None else None
            width = raw.get("width")
            height = raw.get("height")
            photos.append(
                PackagePhotoBytes(
                    capture_photo_id=capture_photo_id,
                    client_file_id=str(raw.get("client_file_id") or capture_photo_id),
                    sequence_number=sequence_number,
                    file_name=file_name,
                    mime_type=str(raw.get("mime_type") or "image/jpeg"),
                    size_bytes=len(content_bytes),
                    sha256=actual_sha,
                    width=int(width) if width is not None else None,
                    height=int(height) if height is not None else None,
                    asset_variant=str(raw.get("asset_variant") or "ORIGINAL").upper(),
                    content=content_bytes,
                )
            )

        # Reject extra undeclared photo files (deterministic packages).
        declared_files = {f"photos/{p.file_name}" for p in photos}
        for name in by_name:
            if name.startswith("photos/") and name not in declared_files:
                raise LocalInventoryPackageError(
                    "PACKAGE_UNDECLARED_PHOTO",
                    f"ZIP contains undeclared photo entry: {name}",
                )

        expected = manifest.get("expected_photo_count", len(photo_meta_list))
        included = manifest.get("included_photo_count", len(photos))
        try:
            expected_i = int(expected)
            included_i = int(included)
        except (TypeError, ValueError) as exc:
            raise LocalInventoryPackageError(
                "PACKAGE_MANIFEST_INVALID",
                "photo count fields must be integers",
            ) from exc
        if included_i != len(photos):
            raise LocalInventoryPackageError(
                "PACKAGE_PHOTO_COUNT_MISMATCH",
                "included_photo_count does not match photos array",
            )
        if expected_i != included_i:
            raise LocalInventoryPackageError(
                "PACKAGE_INCOMPLETE",
                "expected_photo_count != included_photo_count; only COMPLETE packages are accepted",
            )

        return ParsedLocalInventoryPackage(
            package_kind=package_kind,
            package_version=package_version,
            status=status,
            export_id=envelope.export_id,
            inventory_id=envelope.inventory_id,
            aisle_id=envelope.aisle_id,
            capture_session_id=envelope.capture_session_id,
            freeze_id=envelope.freeze_id,
            csv_bytes=csv_bytes,
            csv_checksum_sha256=actual_csv_checksum,
            package_checksum_sha256=(
                str(manifest.get("package_checksum_sha256") or "").strip().lower() or None
            ),
            manifest=manifest,
            photos=tuple(photos),
            expected_photo_count=expected_i,
            included_photo_count=included_i,
        )
