"""Port that applies confirmed local CSV rows to inventory-visible results."""

from __future__ import annotations

from typing import Protocol

from src.domain.local_csv_import.entities import LocalCsvImport, LocalCsvImportRow, LocalCsvProductiveResult


class LocalCsvInventoryResultWriter(Protocol):
    """Writes productive inventory results for confirmed CSV import rows.

    Does not create source assets or photos. Marks unknown product/position as
    requires_review while preserving original codes.
    """

    def apply_import(
        self,
        *,
        record: LocalCsvImport,
        rows_to_import: tuple[LocalCsvImportRow, ...],
        confirmed_by_user_id: str | None,
    ) -> tuple[LocalCsvProductiveResult, ...]: ...

    def list_for_inventory(self, inventory_id: str) -> tuple[LocalCsvProductiveResult, ...]: ...
