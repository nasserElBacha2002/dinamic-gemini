"""Port that applies confirmed local CSV rows to inventory-visible results."""

from __future__ import annotations

from typing import Protocol

from src.domain.local_csv_import.entities import (
    LocalCsvImport,
    LocalCsvImportRow,
    LocalCsvProductiveResult,
)


class LocalCsvInventoryResultWriter(Protocol):
    """Writes productive inventory results for confirmed CSV / package import rows.

    CSV-only imports leave ``has_image_evidence=False``. Package imports may pass
    ``image_evidence_by_import_row_id`` mapping import_row_id → source_asset_id.
    """

    def apply_import(
        self,
        *,
        record: LocalCsvImport,
        rows_to_import: tuple[LocalCsvImportRow, ...],
        confirmed_by_user_id: str | None,
        image_evidence_by_import_row_id: dict[str, str] | None = None,
    ) -> tuple[LocalCsvProductiveResult, ...]: ...

    def list_for_inventory(self, inventory_id: str) -> tuple[LocalCsvProductiveResult, ...]: ...
