"""In-memory repository for local inventory ZIP packages (tests / non-SQL)."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from src.application.ports.local_csv_import_repository import LocalCsvImportRepository
from src.application.ports.local_inventory_package_repository import (
    PackageConfirmEvidenceStager,
    PackageConfirmProductiveApplier,
)
from src.domain.local_csv_import.entities import LocalCsvImport, LocalCsvImportRow
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
        apply_productive: PackageConfirmProductiveApplier,
        clock_now: Callable[[], datetime],
        owner: str,
        lease_sec: int = 120,
        stage_evidence: PackageConfirmEvidenceStager | None = None,
    ) -> tuple[LocalInventoryPackage, bool]:
        policy = (conflict_policy or "SKIP").strip().upper()
        if policy not in CONFLICT_POLICIES:
            raise LocalInventoryPackageImportError(
                "LOCAL_CSV_CONFLICT_POLICY_INVALID",
                f"conflict_policy must be one of: {', '.join(sorted(CONFLICT_POLICIES))}",
            )

        if stage_evidence is None:
            return self._confirm_single_phase(
                inventory_id=inventory_id,
                export_id=export_id,
                conflict_policy=policy,
                confirmed_by_user_id=confirmed_by_user_id,
                apply_productive=apply_productive,
                clock_now=clock_now,
                owner=owner,
                lease_sec=lease_sec,
            )

        planning_pkg: LocalInventoryPackage | None = None
        planning_record: LocalCsvImport | None = None
        planning_rows: tuple[LocalCsvImportRow, ...] = ()

        with self._lock:
            pkg = self._get_pkg_locked(inventory_id=inventory_id, export_id=export_id)
            if pkg.status == "CONFIRMED":
                return self._with_csv(pkg), True
            if pkg.status not in {"PREVIEWED", "MATERIALIZING", "MATERIALIZATION_FAILED"}:
                raise LocalInventoryPackageImportError(
                    "PACKAGE_INVALID_STATUS",
                    f"Package status {pkg.status!r} cannot be confirmed "
                    "(allowed: PREVIEWED|MATERIALIZING|MATERIALIZATION_FAILED → CONFIRMED)",
                )
            record, rows_to_import, csv_confirmed = (
                self._csv_import_repo.select_rows_to_import_on_cursor(  # type: ignore[attr-defined]
                    _MemoryCursor(self._lock),
                    inventory_id=inventory_id,
                    export_id=export_id,
                    conflict_policy=policy,
                )
            )
            if csv_confirmed:
                return self._with_csv(pkg), True
            planning_pkg = pkg
            planning_record = record
            planning_rows = rows_to_import

        assert planning_pkg is not None and planning_record is not None
        stage_evidence(planning_pkg, planning_record, planning_rows)

        return self._confirm_single_phase(
            inventory_id=inventory_id,
            export_id=export_id,
            conflict_policy=policy,
            confirmed_by_user_id=confirmed_by_user_id,
            apply_productive=apply_productive,
            clock_now=clock_now,
            owner=owner,
            lease_sec=lease_sec,
        )

    def _confirm_single_phase(
        self,
        *,
        inventory_id: str,
        export_id: str,
        conflict_policy: str,
        confirmed_by_user_id: str | None,
        apply_productive: PackageConfirmProductiveApplier,
        clock_now: Callable[[], datetime],
        owner: str,
        lease_sec: int,
    ) -> tuple[LocalInventoryPackage, bool]:
        with self._lock:
            pkg = self._get_pkg_locked(inventory_id=inventory_id, export_id=export_id)
            if pkg.status == "CONFIRMED":
                return self._with_csv(pkg), True
            if pkg.status not in {"PREVIEWED", "MATERIALIZING", "MATERIALIZATION_FAILED"}:
                raise LocalInventoryPackageImportError(
                    "PACKAGE_INVALID_STATUS",
                    f"Package status {pkg.status!r} cannot be confirmed "
                    "(allowed: PREVIEWED|MATERIALIZING|MATERIALIZATION_FAILED → CONFIRMED)",
                )

            csv_record, duplicate = self._csv_import_repo.confirm_import_atomically(
                inventory_id=inventory_id,
                export_id=export_id,
                conflict_policy=conflict_policy,
                confirmed_by_user_id=confirmed_by_user_id,
                apply_productive=lambda record, rows_to_import, confirmed_by_user_id, *, cursor=None: (
                    apply_productive(
                        record, rows_to_import, confirmed_by_user_id, pkg, cursor=cursor
                    )
                ),
                clock_now=clock_now,
                cursor=_MemoryCursor(self._lock),
                owner=owner,
                lease_sec=lease_sec,
            )
            now = clock_now()
            claimed = replace(
                pkg,
                status="MATERIALIZING",
                confirmed_at=None,
                confirmed_by_user_id=confirmed_by_user_id,
                materialization_owner=csv_record.materialization_owner,
                materialization_lease_expires_at=csv_record.materialization_lease_expires_at,
                fencing_version=int(csv_record.fencing_version or 0),
                updated_at=now,
                photos=tuple(pkg.photos),
                csv_import=csv_record,
            )
            self._by_id[claimed.id] = claimed
            return claimed, duplicate

    def finalize_package_confirmation(
        self,
        *,
        package_id: str,
        clock_now: Callable[[], datetime],
        confirmed_by_user_id: str | None = None,
        owner: str | None = None,
        expected_fencing_version: int | None = None,
    ) -> LocalInventoryPackage:
        with self._lock:
            pkg = self._by_id.get(package_id)
            if pkg is None:
                raise LocalInventoryPackageImportError(
                    PACKAGE_NOT_FOUND, "Package not found"
                )
            now = clock_now()
            csv_import = self._csv_import_repo.finalize_import_confirmation_on_cursor(
                _MemoryCursor(self._lock),
                import_id=pkg.csv_import_id,
                clock_now=clock_now,
                confirmed_by_user_id=confirmed_by_user_id,
                owner=owner,
                expected_fencing_version=expected_fencing_version,
            )
            if pkg.status != "CONFIRMED":
                confirmed = replace(
                    pkg,
                    status="CONFIRMED",
                    confirmed_at=now,
                    confirmed_by_user_id=confirmed_by_user_id or pkg.confirmed_by_user_id,
                    updated_at=now,
                    csv_import=csv_import,
                )
                self._by_id[confirmed.id] = confirmed
                return confirmed
            return self._with_csv(replace(pkg, csv_import=csv_import))

    def mark_materialization_failed(
        self,
        *,
        package_id: str,
        error_code: str,
        clock_now: Callable[[], datetime],
        requires_review: bool = False,
        next_retry_at: datetime | None = None,
        owner: str | None = None,
        expected_fencing_version: int | None = None,
    ) -> LocalInventoryPackage:
        with self._lock:
            pkg = self._by_id.get(package_id)
            if pkg is None:
                raise LocalInventoryPackageImportError(
                    PACKAGE_NOT_FOUND, "Package not found"
                )
            if pkg.status == "CONFIRMED":
                return self._with_csv(pkg)
            now = clock_now()
            csv_import = self._csv_import_repo.mark_materialization_failed_on_cursor(
                _MemoryCursor(self._lock),
                import_id=pkg.csv_import_id,
                error_code=error_code,
                clock_now=clock_now,
                requires_review=requires_review,
                next_retry_at=next_retry_at,
                owner=owner,
                expected_fencing_version=expected_fencing_version,
            )
            failed_status = (
                "REQUIRES_REVIEW" if requires_review else "MATERIALIZATION_FAILED"
            )
            failed = replace(
                pkg,
                status=failed_status,
                updated_at=now,
                csv_import=csv_import,
            )
            self._by_id[failed.id] = failed
            return failed

    def _get_pkg_locked(self, *, inventory_id: str, export_id: str) -> LocalInventoryPackage:
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
        return pkg

    def _with_csv(self, pkg: LocalInventoryPackage) -> LocalInventoryPackage:
        csv_import = self._csv_import_repo.get_by_id(pkg.csv_import_id)
        return replace(pkg, csv_import=csv_import)


class _MemoryCursor:
    """Placeholder cursor token — memory repos use repo-level locks instead."""

    def __init__(self, lock: threading.Lock) -> None:
        self._lock = lock

    def execute(self, *args, **kwargs) -> None:
        _ = args, kwargs

    def executemany(self, *args, **kwargs) -> None:
        _ = args, kwargs

    def fetchone(self) -> None:
        return None

    def fetchall(self) -> list[object]:
        return []

    @property
    def rowcount(self) -> int:
        return 0
