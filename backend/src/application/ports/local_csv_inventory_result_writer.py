"""Port that applies confirmed local CSV rows to inventory-visible results."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from src.application.ports.sql_cursor import SqlCursorLike
from src.domain.local_csv_import.entities import (
    LocalCsvImport,
    LocalCsvImportRow,
    LocalCsvProductiveResult,
)


class LocalCsvInventoryResultWriter(Protocol):
    """Writes productive inventory results for confirmed CSV / package import rows.

    CSV-only imports leave ``has_image_evidence=False``. Package imports may pass
    ``image_evidence_by_import_row_id`` mapping import_row_id → source_asset_id.

    When ``cursor`` is provided, SQL implementations MUST use that cursor only
    (no nested connection / commit).
    """

    def apply_import(
        self,
        *,
        record: LocalCsvImport,
        rows_to_import: tuple[LocalCsvImportRow, ...],
        confirmed_by_user_id: str | None,
        image_evidence_by_import_row_id: dict[str, str] | None = None,
        cursor: SqlCursorLike | None = None,
    ) -> tuple[LocalCsvProductiveResult, ...]: ...

    def list_for_inventory(self, inventory_id: str) -> tuple[LocalCsvProductiveResult, ...]: ...

    def list_for_import(self, import_id: str) -> tuple[LocalCsvProductiveResult, ...]: ...

    def aisle_ids_with_ingestion_source(
        self,
        inventory_id: str,
        aisle_ids: Sequence[str],
        ingestion_source: str,
    ) -> frozenset[str]: ...
