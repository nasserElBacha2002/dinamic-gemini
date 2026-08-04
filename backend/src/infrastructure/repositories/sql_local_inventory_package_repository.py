"""SQL Server repository for local inventory ZIP packages."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone

from src.application.ports.local_csv_import_repository import LocalCsvImportRepository
from src.domain.local_csv_import.entities import (
    LocalCsvImport,
    LocalCsvImportRow,
    LocalCsvProductiveResult,
)
from src.domain.local_csv_import.errors import CONFLICT_POLICIES
from src.domain.local_inventory_package.entities import (
    LocalInventoryPackage,
    LocalInventoryPackagePhoto,
)
from src.domain.local_inventory_package.errors import (
    PACKAGE_EXPORT_CONFLICT,
    PACKAGE_NOT_FOUND,
    LocalInventoryPackageImportError,
)
from src.infrastructure.database.sql_transaction import sql_repository_cursor


def _utc(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def _photo_from_db(row: object) -> LocalInventoryPackagePhoto:
    return LocalInventoryPackagePhoto(
        id=str(getattr(row, "id")),
        package_id=str(getattr(row, "package_id")),
        capture_photo_id=str(getattr(row, "capture_photo_id")),
        client_file_id=str(getattr(row, "client_file_id")),
        sequence_number=(
            int(getattr(row, "sequence_number"))
            if getattr(row, "sequence_number", None) is not None
            else None
        ),
        file_name=str(getattr(row, "file_name")),
        mime_type=str(getattr(row, "mime_type")),
        size_bytes=int(getattr(row, "size_bytes")),
        sha256=str(getattr(row, "sha256")),
        width=int(getattr(row, "width")) if getattr(row, "width", None) is not None else None,
        height=int(getattr(row, "height")) if getattr(row, "height", None) is not None else None,
        asset_variant=str(getattr(row, "asset_variant")),
        staging_path=str(getattr(row, "staging_path")),
        source_asset_id=(
            str(getattr(row, "source_asset_id"))
            if getattr(row, "source_asset_id", None) is not None
            else None
        ),
    )


def _package_from_db(
    row: object, photos: tuple[LocalInventoryPackagePhoto, ...]
) -> LocalInventoryPackage:
    return LocalInventoryPackage(
        id=str(getattr(row, "id")),
        inventory_id=str(getattr(row, "inventory_id")),
        export_id=str(getattr(row, "export_id")),
        csv_import_id=str(getattr(row, "csv_import_id")),
        package_kind=str(getattr(row, "package_kind")),
        package_version=int(getattr(row, "package_version")),
        status=str(getattr(row, "status")),
        package_checksum_sha256=(
            str(getattr(row, "package_checksum_sha256"))
            if getattr(row, "package_checksum_sha256", None) is not None
            else None
        ),
        csv_checksum_sha256=str(getattr(row, "csv_checksum_sha256")),
        expected_photo_count=int(getattr(row, "expected_photo_count")),
        included_photo_count=int(getattr(row, "included_photo_count")),
        aisle_id=(
            str(getattr(row, "aisle_id")) if getattr(row, "aisle_id", None) is not None else None
        ),
        capture_session_id=(
            str(getattr(row, "capture_session_id"))
            if getattr(row, "capture_session_id", None) is not None
            else None
        ),
        freeze_id=(
            str(getattr(row, "freeze_id")) if getattr(row, "freeze_id", None) is not None else None
        ),
        staging_dir=str(getattr(row, "staging_dir")),
        created_at=_utc(getattr(row, "created_at")),
        updated_at=_utc(getattr(row, "updated_at")),
        confirmed_at=(
            _utc(getattr(row, "confirmed_at"))
            if getattr(row, "confirmed_at", None) is not None
            else None
        ),
        confirmed_by_user_id=(
            str(getattr(row, "confirmed_by_user_id"))
            if getattr(row, "confirmed_by_user_id", None) is not None
            else None
        ),
        photos=photos,
    )


_PKG_COLS = (
    "id, inventory_id, export_id, csv_import_id, package_kind, package_version, status, "
    "package_checksum_sha256, csv_checksum_sha256, expected_photo_count, included_photo_count, "
    "aisle_id, capture_session_id, freeze_id, staging_dir, confirmed_at, confirmed_by_user_id, "
    "created_at, updated_at"
)


class SqlLocalInventoryPackageRepository:
    def __init__(
        self, client: object, *, csv_import_repo: LocalCsvImportRepository
    ) -> None:
        self._client = client
        self._csv_import_repo = csv_import_repo

    def get_by_id(self, package_id: str) -> LocalInventoryPackage | None:
        with self._client.cursor() as cur:  # type: ignore[attr-defined]
            cur.execute(
                f"SELECT {_PKG_COLS} FROM local_inventory_packages WHERE id = ?",
                (package_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return self._hydrate(cur, row)

    def get_by_export_id(
        self, *, inventory_id: str, export_id: str
    ) -> LocalInventoryPackage | None:
        with self._client.cursor() as cur:  # type: ignore[attr-defined]
            cur.execute(
                f"SELECT {_PKG_COLS} FROM local_inventory_packages "
                "WHERE inventory_id = ? AND export_id = ?",
                (inventory_id, export_id),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return self._hydrate(cur, row)

    def stage_or_get_existing(self, record: LocalInventoryPackage) -> LocalInventoryPackage:
        existing = self.get_by_export_id(
            inventory_id=record.inventory_id, export_id=record.export_id
        )
        if existing is not None:
            if (existing.package_checksum_sha256 or existing.csv_checksum_sha256) != (
                record.package_checksum_sha256 or record.csv_checksum_sha256
            ):
                raise LocalInventoryPackageImportError(
                    PACKAGE_EXPORT_CONFLICT,
                    "export_id already exists with different package content",
                )
            return existing
        with sql_repository_cursor(self._client) as cur:  # type: ignore[arg-type]
            self._persist(cur, record)
        return self.get_by_id(record.id) or record

    def confirm_package_atomically(
        self,
        *,
        inventory_id: str,
        export_id: str,
        conflict_policy: str,
        confirmed_by_user_id: str | None,
        apply_productive: Callable[
            [LocalCsvImport, tuple[LocalCsvImportRow, ...], str | None, LocalInventoryPackage],
            tuple[LocalCsvProductiveResult, ...],
        ],
        clock_now: Callable[[], datetime],
    ) -> tuple[LocalInventoryPackage, bool]:
        policy = (conflict_policy or "SKIP").strip().upper()
        if policy not in CONFLICT_POLICIES:
            raise LocalInventoryPackageImportError(
                "LOCAL_CSV_CONFLICT_POLICY_INVALID",
                f"conflict_policy must be one of: {', '.join(sorted(CONFLICT_POLICIES))}",
            )
        pkg = self.get_by_export_id(inventory_id=inventory_id, export_id=export_id)
        if pkg is None:
            raise LocalInventoryPackageImportError(
                PACKAGE_NOT_FOUND, "Package not found for export_id"
            )
        if pkg.status == "CONFIRMED":
            return pkg, True

        csv_record, duplicate = self._csv_import_repo.confirm_import_atomically(
            inventory_id=inventory_id,
            export_id=export_id,
            conflict_policy=policy,
            confirmed_by_user_id=confirmed_by_user_id,
            apply_productive=lambda record, rows, user_id: apply_productive(
                record, rows, user_id, pkg
            ),
            clock_now=clock_now,  # type: ignore[arg-type]
        )
        now = clock_now()
        assert isinstance(now, datetime)
        with sql_repository_cursor(self._client) as cur:  # type: ignore[arg-type]
            cur.execute(
                "UPDATE local_inventory_packages SET status=?, confirmed_at=?, "
                "confirmed_by_user_id=?, updated_at=? WHERE id=?",
                ("CONFIRMED", now, confirmed_by_user_id, now, pkg.id),
            )
        confirmed = replace(
            pkg,
            status="CONFIRMED",
            confirmed_at=now,
            confirmed_by_user_id=confirmed_by_user_id,
            updated_at=now,
            csv_import=csv_record,
        )
        return confirmed, duplicate

    def _hydrate(self, cur: object, row: object) -> LocalInventoryPackage:
        cur.execute(  # type: ignore[attr-defined]
            "SELECT id, package_id, capture_photo_id, client_file_id, sequence_number, "
            "file_name, mime_type, size_bytes, sha256, width, height, asset_variant, "
            "staging_path, source_asset_id "
            "FROM local_inventory_package_photos WHERE package_id = ? "
            "ORDER BY sequence_number, file_name",
            (str(getattr(row, "id")),),
        )
        photos = tuple(_photo_from_db(r) for r in cur.fetchall())  # type: ignore[attr-defined]
        pkg = _package_from_db(row, photos)
        csv_import = self._csv_import_repo.get_by_id(pkg.csv_import_id)
        return replace(pkg, csv_import=csv_import)

    def _persist(self, cur: object, record: LocalInventoryPackage) -> None:
        cur.execute(  # type: ignore[attr-defined]
            "INSERT INTO local_inventory_packages "
            "(id, inventory_id, export_id, csv_import_id, package_kind, package_version, status, "
            "package_checksum_sha256, csv_checksum_sha256, expected_photo_count, "
            "included_photo_count, aisle_id, capture_session_id, freeze_id, staging_dir, "
            "confirmed_at, confirmed_by_user_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record.id,
                record.inventory_id,
                record.export_id,
                record.csv_import_id,
                record.package_kind,
                record.package_version,
                record.status,
                record.package_checksum_sha256,
                record.csv_checksum_sha256,
                record.expected_photo_count,
                record.included_photo_count,
                record.aisle_id,
                record.capture_session_id,
                record.freeze_id,
                record.staging_dir,
                record.confirmed_at,
                record.confirmed_by_user_id,
                record.created_at,
                record.updated_at,
            ),
        )
        for photo in record.photos:
            cur.execute(  # type: ignore[attr-defined]
                "INSERT INTO local_inventory_package_photos "
                "(id, package_id, capture_photo_id, client_file_id, sequence_number, file_name, "
                "mime_type, size_bytes, sha256, width, height, asset_variant, staging_path, "
                "source_asset_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    photo.id,
                    photo.package_id,
                    photo.capture_photo_id,
                    photo.client_file_id,
                    photo.sequence_number,
                    photo.file_name,
                    photo.mime_type,
                    photo.size_bytes,
                    photo.sha256,
                    photo.width,
                    photo.height,
                    photo.asset_variant,
                    photo.staging_path,
                    photo.source_asset_id,
                ),
            )
