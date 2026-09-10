"""Port for staging local inventory ZIP packages between preview and confirm."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from src.application.ports.sql_cursor import SqlCursorLike
from src.domain.local_csv_import.entities import (
    LocalCsvImport,
    LocalCsvImportRow,
    LocalCsvProductiveResult,
)
from src.domain.local_inventory_package.entities import LocalInventoryPackage


class PackageConfirmProductiveApplier(Protocol):
    def __call__(
        self,
        record: LocalCsvImport,
        rows_to_import: tuple[LocalCsvImportRow, ...],
        confirmed_by_user_id: str | None,
        package: LocalInventoryPackage,
        *,
        cursor: SqlCursorLike | None = None,
    ) -> tuple[LocalCsvProductiveResult, ...]: ...


class PackageConfirmEvidenceStager(Protocol):
    """Create SourceAssets only for rows already selected for import (outside SQL locks)."""

    def __call__(
        self,
        package: LocalInventoryPackage,
        record: LocalCsvImport,
        rows_to_import: tuple[LocalCsvImportRow, ...],
    ) -> dict[str, str]:
        """Return capture_photo_id → source_asset_id."""
        ...


class LocalInventoryPackageRepository(Protocol):
    def get_by_id(self, package_id: str) -> LocalInventoryPackage | None: ...

    def get_by_export_id(
        self, *, inventory_id: str, export_id: str
    ) -> LocalInventoryPackage | None: ...

    def stage_or_get_existing(self, record: LocalInventoryPackage) -> LocalInventoryPackage: ...

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
        """Confirm package + CSV under one final SQL transaction.

        When ``stage_evidence`` is provided, conflict resolution runs first under a
        short planning lock, evidence is staged outside locks for ``rows_to_import``
        only, then the apply/confirm transaction revalidates under lock.

        Lock order on apply: package → csv import.

        Returns MATERIALIZING until ``finalize_package_confirmation`` runs.
        """
        ...

    def finalize_package_confirmation(
        self,
        *,
        package_id: str,
        clock_now: Callable[[], datetime],
        confirmed_by_user_id: str | None = None,
        owner: str | None = None,
        expected_fencing_version: int | None = None,
    ) -> LocalInventoryPackage:
        """MATERIALIZING → CONFIRMED for package and linked CSV import in one transaction.

        Finalizes the linked CSV import on the same SQL cursor before updating the
        package header. When the CSV is already CONFIRMED but the package is not,
        completes the package repair in the same transaction.
        """
        ...

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
        """Persist failure on package + linked CSV import atomically."""
        ...
