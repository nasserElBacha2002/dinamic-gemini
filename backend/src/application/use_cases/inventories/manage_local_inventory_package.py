"""Preview, confirm, and fetch local inventory ZIP packages."""

from __future__ import annotations

import hashlib
import tempfile
import uuid
from pathlib import Path

from src.application.dto.uploaded_file import UploadedFile
from src.application.ports.clock import Clock
from src.application.ports.local_csv_import_repository import LocalCsvImportRepository
from src.application.ports.local_csv_inventory_result_writer import LocalCsvInventoryResultWriter
from src.application.ports.local_inventory_package_repository import LocalInventoryPackageRepository
from src.application.ports.repositories import AisleRepository, InventoryRepository
from src.application.services.aisle_source_asset_materializer import AisleSourceAssetMaterializer
from src.application.services.local_csv_parser import LocalCsvDocumentError
from src.application.services.local_inventory_package_parser import (
    LocalInventoryPackageError,
    ParsedLocalInventoryPackage,
    parse_local_inventory_package,
)
from src.application.use_cases.inventories.manage_local_csv_import import PreviewLocalCsvImport
from src.domain.local_csv_import.entities import LocalCsvImport, LocalCsvImportRow, LocalCsvProductiveResult
from src.domain.local_csv_import.errors import CONFLICT_POLICIES
from src.domain.local_inventory_package.entities import (
    LocalInventoryPackage,
    LocalInventoryPackagePhoto,
)
from src.domain.local_inventory_package.errors import (
    PACKAGE_INVENTORY_MISMATCH,
    PACKAGE_NOT_FOUND,
    LocalInventoryPackageDisabledError,
    LocalInventoryPackageImportError,
)


class PreviewLocalInventoryPackage:
    def __init__(
        self,
        *,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        csv_import_repo: LocalCsvImportRepository,
        package_repo: LocalInventoryPackageRepository,
        csv_preview: PreviewLocalCsvImport,
        clock: Clock,
        enabled: bool,
        staging_root: Path | None = None,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._csv_import_repo = csv_import_repo
        self._package_repo = package_repo
        self._csv_preview = csv_preview
        self._clock = clock
        self._enabled = enabled
        self._staging_root = staging_root

    def execute(self, *, inventory_id: str, content: bytes) -> LocalInventoryPackage:
        if not self._enabled:
            raise LocalInventoryPackageDisabledError()
        if self._inventory_repo.get_by_id(inventory_id) is None:
            raise LocalInventoryPackageImportError(
                "INVENTORY_NOT_FOUND", f"Inventory {inventory_id} not found"
            )
        try:
            parsed = parse_local_inventory_package(content)
        except LocalInventoryPackageError as exc:
            raise LocalInventoryPackageImportError(exc.code, str(exc)) from exc

        if parsed.inventory_id != inventory_id:
            raise LocalInventoryPackageImportError(
                PACKAGE_INVENTORY_MISMATCH,
                "Package inventory_id does not match the path inventory_id",
            )

        existing = self._package_repo.get_by_export_id(
            inventory_id=inventory_id, export_id=parsed.export_id
        )
        if existing is not None:
            existing_fp = existing.package_checksum_sha256 or existing.csv_checksum_sha256
            new_fp = parsed.package_checksum_sha256 or parsed.csv_checksum_sha256
            if existing_fp != new_fp:
                raise LocalInventoryPackageImportError(
                    "LOCAL_INVENTORY_PACKAGE_EXPORT_CONFLICT",
                    "export_id already exists with different package content",
                )
            return existing

        try:
            csv_record = self._csv_preview.execute(
                inventory_id=inventory_id, content=parsed.csv_bytes
            )
        except LocalCsvDocumentError as exc:
            raise LocalInventoryPackageImportError(exc.code, str(exc)) from exc

        self._validate_photo_row_linkage(csv_record, parsed)
        aisle_id = self._resolve_package_aisle_id(
            inventory_id=inventory_id,
            manifest_aisle_id=parsed.aisle_id,
            csv_record=csv_record,
        )

        package_id = str(uuid.uuid4())
        staging_dir = self._make_staging_dir(package_id)
        photos = self._stage_photos(package_id, staging_dir, parsed)
        now = self._clock.now()
        record = LocalInventoryPackage(
            id=package_id,
            inventory_id=inventory_id,
            export_id=parsed.export_id,
            csv_import_id=csv_record.id,
            package_kind=parsed.package_kind,
            package_version=parsed.package_version,
            status="PREVIEWED",
            package_checksum_sha256=parsed.package_checksum_sha256,
            csv_checksum_sha256=parsed.csv_checksum_sha256,
            expected_photo_count=parsed.expected_photo_count,
            included_photo_count=parsed.included_photo_count,
            aisle_id=aisle_id,
            capture_session_id=parsed.capture_session_id,
            freeze_id=parsed.freeze_id,
            staging_dir=str(staging_dir),
            created_at=now,
            updated_at=now,
            photos=photos,
            csv_import=csv_record,
        )
        return self._package_repo.stage_or_get_existing(record)

    def _resolve_package_aisle_id(
        self,
        *,
        inventory_id: str,
        manifest_aisle_id: str | None,
        csv_record: LocalCsvImport,
    ) -> str:
        candidates: set[str] = set()
        if manifest_aisle_id and str(manifest_aisle_id).strip():
            candidates.add(str(manifest_aisle_id).strip())
        for row in csv_record.rows:
            if row.status == "REJECTED":
                continue
            aid = (row.aisle_id or "").strip()
            if aid:
                candidates.add(aid)
        if not candidates:
            raise LocalInventoryPackageImportError(
                "PACKAGE_AISLE_REQUIRED",
                "Package must declare a single aisle_id (manifest or CSV rows)",
            )
        if len(candidates) > 1:
            raise LocalInventoryPackageImportError(
                "PACKAGE_AISLE_AMBIGUOUS",
                "Package references more than one aisle_id; import one aisle per ZIP",
            )
        aisle_id = next(iter(candidates))
        aisle = self._aisle_repo.get_by_id(aisle_id)
        if aisle is None or aisle.inventory_id != inventory_id:
            raise LocalInventoryPackageImportError(
                "PACKAGE_AISLE_NOT_FOUND",
                f"Aisle {aisle_id} was not found in this inventory",
            )
        return aisle_id

    def _make_staging_dir(self, package_id: str) -> Path:
        root = self._staging_root or Path(tempfile.gettempdir()) / "dinamic_local_packages"
        path = root / package_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _stage_photos(
        self,
        package_id: str,
        staging_dir: Path,
        parsed: ParsedLocalInventoryPackage,
    ) -> tuple[LocalInventoryPackagePhoto, ...]:
        photos: list[LocalInventoryPackagePhoto] = []
        for photo in parsed.photos:
            safe_name = Path(photo.file_name).name
            dest = staging_dir / safe_name
            dest.write_bytes(photo.content)
            photos.append(
                LocalInventoryPackagePhoto(
                    id=str(uuid.uuid4()),
                    package_id=package_id,
                    capture_photo_id=photo.capture_photo_id,
                    client_file_id=photo.client_file_id,
                    sequence_number=photo.sequence_number,
                    file_name=safe_name,
                    mime_type=photo.mime_type,
                    size_bytes=photo.size_bytes,
                    sha256=photo.sha256,
                    width=photo.width,
                    height=photo.height,
                    asset_variant=photo.asset_variant,
                    staging_path=str(dest),
                )
            )
        return tuple(photos)

    @staticmethod
    def _validate_photo_row_linkage(
        csv_record: LocalCsvImport, parsed: ParsedLocalInventoryPackage
    ) -> None:
        by_photo = {p.capture_photo_id: p for p in parsed.photos}
        for row in csv_record.rows:
            if row.status == "REJECTED":
                continue
            if row.capture_photo_id not in by_photo:
                raise LocalInventoryPackageImportError(
                    "PACKAGE_ROW_PHOTO_MISSING",
                    f"CSV row {row.row_number} has no matching package photo "
                    f"for capture_photo_id={row.capture_photo_id}",
                )


class ConfirmLocalInventoryPackage:
    def __init__(
        self,
        *,
        package_repo: LocalInventoryPackageRepository,
        result_writer: LocalCsvInventoryResultWriter,
        materializer: AisleSourceAssetMaterializer,
        aisle_repo: AisleRepository,
        clock: Clock,
        enabled: bool,
    ) -> None:
        self._package_repo = package_repo
        self._result_writer = result_writer
        self._materializer = materializer
        self._aisle_repo = aisle_repo
        self._clock = clock
        self._enabled = enabled

    def execute(
        self,
        *,
        inventory_id: str,
        export_id: str,
        conflict_policy: str = "SKIP",
        confirmed_by_user_id: str | None = None,
    ) -> tuple[LocalInventoryPackage, bool]:
        if not self._enabled:
            raise LocalInventoryPackageDisabledError()
        policy = (conflict_policy or "SKIP").strip().upper()
        if policy not in CONFLICT_POLICIES:
            raise LocalInventoryPackageImportError(
                "LOCAL_CSV_CONFLICT_POLICY_INVALID",
                f"conflict_policy must be one of: {', '.join(sorted(CONFLICT_POLICIES))}",
            )
        return self._package_repo.confirm_package_atomically(
            inventory_id=inventory_id,
            export_id=export_id.strip(),
            conflict_policy=policy,
            confirmed_by_user_id=confirmed_by_user_id,
            apply_productive=self._apply_productive,
            clock_now=self._clock.now,
        )

    def _apply_productive(
        self,
        record: LocalCsvImport,
        rows_to_import: tuple[LocalCsvImportRow, ...],
        confirmed_by_user_id: str | None,
        package: LocalInventoryPackage,
    ) -> tuple[LocalCsvProductiveResult, ...]:
        now = self._clock.now()
        photos_by_capture = {p.capture_photo_id: p for p in package.photos}
        evidence: dict[str, str] = {}
        # source_assets.upload_batch_id is VARCHAR(36); package.id is already a UUID.
        upload_batch_id = package.id
        aisle_ids: set[str] = set()

        for row in rows_to_import:
            photo = photos_by_capture.get(row.capture_photo_id)
            if photo is None:
                continue
            path = Path(photo.staging_path)
            if not path.is_file():
                raise LocalInventoryPackageImportError(
                    "PACKAGE_STAGING_MISSING",
                    f"Staged photo missing: {photo.file_name}",
                )
            with path.open("rb") as handle:
                uploaded = UploadedFile(
                    original_filename=photo.file_name,
                    file_obj=handle,
                    content_type=photo.mime_type or "image/jpeg",
                    client_file_id=photo.client_file_id,
                    upload_batch_id=upload_batch_id,
                    size_bytes=photo.size_bytes,
                    content_sha256=photo.sha256,
                    # Do not set ordered_capture_session_id: mobile session IDs are not
                    # server ordered_capture_sessions rows (FK would fail).
                    sequence_number=photo.sequence_number or row.capture_order,
                )
                asset, _rollback = self._materializer.persist_uploaded_file_as_source_asset(
                    aisle_id=row.aisle_id,
                    uploaded=uploaded,
                    now=now,
                    metadata_json={
                        "local_package_id": package.id,
                        "capture_photo_id": photo.capture_photo_id,
                        "capture_session_id": row.capture_session_id,
                        "asset_variant": photo.asset_variant,
                        "package_photo_sha256": photo.sha256,
                        "content_sha256": photo.sha256,
                    },
                    upload_batch_id=upload_batch_id,
                    upload_client_file_id=photo.client_file_id,
                    sequence_number=photo.sequence_number or row.capture_order,
                    sequence_source="CLIENT_ASSIGNED",
                )
            evidence[row.id] = asset.id
            aisle_ids.add(row.aisle_id)

        results = self._result_writer.apply_import(
            record=record,
            rows_to_import=rows_to_import,
            confirmed_by_user_id=confirmed_by_user_id,
            image_evidence_by_import_row_id=evidence,
        )
        for aisle_id in aisle_ids:
            aisle = self._aisle_repo.get_by_id(aisle_id)
            if aisle is not None:
                self._materializer.finalize_aisle_after_source_assets_changed(
                    aisle=aisle,
                    inventory_id=record.inventory_id,
                    now=now,
                )
        return results


class GetLocalInventoryPackage:
    def __init__(
        self, *, package_repo: LocalInventoryPackageRepository, enabled: bool
    ) -> None:
        self._package_repo = package_repo
        self._enabled = enabled

    def execute(self, *, inventory_id: str, package_id: str) -> LocalInventoryPackage:
        if not self._enabled:
            raise LocalInventoryPackageDisabledError()
        record = self._package_repo.get_by_id(package_id)
        if record is None or record.inventory_id != inventory_id:
            raise LocalInventoryPackageImportError(PACKAGE_NOT_FOUND, "Package not found")
        return record


def package_content_fingerprint(parsed: ParsedLocalInventoryPackage) -> str:
    photo_part = ",".join(f"{p.capture_photo_id}:{p.sha256}" for p in parsed.photos)
    raw = f"pkg-v{parsed.package_version}|{parsed.freeze_id or ''}|{parsed.csv_checksum_sha256}|{photo_part}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
