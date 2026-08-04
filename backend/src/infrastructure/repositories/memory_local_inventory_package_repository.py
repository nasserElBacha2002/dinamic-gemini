"""In-memory repository for local inventory ZIP packages (tests / non-SQL)."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from src.application.ports.local_csv_import_repository import LocalCsvImportRepository
from src.domain.local_csv_import.entities import (
    LocalCsvImport,
    LocalCsvImportRow,
    LocalCsvProductiveResult,
)
from src.domain.local_csv_import.errors import CONFLICT_POLICIES
from src.domain.local_inventory_package.entities import LocalInventoryPackage
from src.domain.local_inventory_package.errors import (
    PACKAGE_EXPORT_CONFLICT,
    PACKAGE_NOT_FOUND,
    LocalInventoryPackageImportError,
)


class MemoryLocalInventoryPackageRepository:
    def __init__(self, *, csv_import_repo: LocalCsvImportRepository) -> None:
        self._csv_import_repo = csv_import_repo
        self._by_id: dict[str, LocalInventoryPackage] = {}
        self._lock = threading.Lock()

    def get_by_id(self, package_id: str) -> LocalInventoryPackage | None:
        with self._lock:
            pkg = self._by_id.get(package_id)
            return self._with_csv(pkg) if pkg else None

    def get_by_export_id(
        self, *, inventory_id: str, export_id: str
    ) -> LocalInventoryPackage | None:
        with self._lock:
            for pkg in self._by_id.values():
                if pkg.inventory_id == inventory_id and pkg.export_id == export_id:
                    return self._with_csv(pkg)
            return None

    def stage_or_get_existing(self, record: LocalInventoryPackage) -> LocalInventoryPackage:
        with self._lock:
            for existing in self._by_id.values():
                if (
                    existing.inventory_id == record.inventory_id
                    and existing.export_id == record.export_id
                ):
                    if existing.package_checksum_sha256 != record.package_checksum_sha256:
                        raise LocalInventoryPackageImportError(
                            PACKAGE_EXPORT_CONFLICT,
                            "export_id already exists with different package content",
                        )
                    return self._with_csv(existing)
            self._by_id[record.id] = record
            return self._with_csv(record)

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
        with self._lock:
            pkg = next(
                (
                    p
                    for p in self._by_id.values()
                    if p.inventory_id == inventory_id and p.export_id == export_id
                ),
                None,
            )
            if pkg is None:
                raise LocalInventoryPackageImportError(
                    PACKAGE_NOT_FOUND, "Package not found for export_id"
                )
            if pkg.status == "CONFIRMED":
                return self._with_csv(pkg), True

            csv_record, duplicate = self._csv_import_repo.confirm_import_atomically(
                inventory_id=inventory_id,
                export_id=export_id,
                conflict_policy=policy,
                confirmed_by_user_id=confirmed_by_user_id,
                apply_productive=lambda record, rows, user_id: apply_productive(
                    record, rows, user_id, pkg
                ),
                clock_now=clock_now,
            )
            now = clock_now()
            updated_photos = []
            # source_asset_id is filled by apply_productive via side-effect on photos list
            # carried in package; re-read from apply result metadata if present.
            for photo in pkg.photos:
                updated_photos.append(photo)
            confirmed = replace(
                pkg,
                status="CONFIRMED",
                confirmed_at=now,
                confirmed_by_user_id=confirmed_by_user_id,
                updated_at=now,
                photos=tuple(updated_photos),
                csv_import=csv_record,
            )
            self._by_id[confirmed.id] = confirmed
            return confirmed, duplicate

    def _with_csv(self, pkg: LocalInventoryPackage) -> LocalInventoryPackage:
        csv_import = self._csv_import_repo.get_by_id(pkg.csv_import_id)
        return replace(pkg, csv_import=csv_import)
