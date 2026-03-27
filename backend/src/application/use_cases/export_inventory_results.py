"""
Export consolidated inventory results as CSV (v3).

Uses the same SKU consolidation as ``ListAislePositionsUseCase`` and summary mapping as
``position_to_summary`` (via ``inventory_export_rows``).

**Ordering (deterministic, operator-friendly):**
There is no explicit aisle ``display_order`` on the domain model today. Aisles are ordered by
``natural_sort_key_parts(aisle.code)``, then ``aisle.created_at``, then ``aisle.id``. Exported
``aisle_sequence`` is 1-based index in that order. Within an aisle, positions use
``export_position_sort_key``: natural sort on the human-facing position code (``pallet_id`` →
``position_barcode`` → ``entity_uid``), then ``internal_code``, ``created_at``, ``id``.
``final_quantity`` is ``corrected_quantity`` when set on the primary product row, otherwise the same
``final_quantity`` as ``position_to_summary`` (detected/aggregated path).
"""

from __future__ import annotations

from collections import defaultdict
from typing import DefaultDict, List

from src.application.errors import InventoryNotFoundError
from src.application.mappers.inventory_export_rows import export_position_sort_key, position_to_export_row_dict
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    PositionRepository,
    ProductRecordRepository,
)
from src.application.services.csv_inventory_exporter import CsvInventoryExporter
from src.application.use_cases.list_aisle_positions import _consolidate_by_sku
from src.application.utils.natural_sort import natural_sort_key_parts
from src.domain.positions.entities import Position, PositionStatus


class ExportInventoryResultsUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        position_repo: PositionRepository,
        product_record_repo: ProductRecordRepository,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._position_repo = position_repo
        self._product_record_repo = product_record_repo

    def execute_csv(self, inventory_id: str) -> str:
        inv = self._inventory_repo.get_by_id(inventory_id)
        if inv is None:
            raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")

        aisles = list(self._aisle_repo.list_by_inventory(inventory_id))
        sorted_aisles = sorted(
            aisles,
            key=lambda a: (natural_sort_key_parts(a.code), a.created_at, a.id),
        )
        aisle_ids = [a.id for a in sorted_aisles]
        all_positions = list(self._position_repo.list_by_aisles(aisle_ids))
        by_aisle: DefaultDict[str, List[Position]] = defaultdict(list)
        for p in all_positions:
            by_aisle[p.aisle_id].append(p)

        rows: List[dict] = []
        for seq, aisle in enumerate(sorted_aisles, start=1):
            raw = [p for p in by_aisle.get(aisle.id, []) if p.status != PositionStatus.DELETED]
            consolidated = _consolidate_by_sku(raw)
            consolidated_sorted = sorted(consolidated, key=export_position_sort_key)
            for p in consolidated_sorted:
                products = self._product_record_repo.list_by_position(p.id)
                primary = (
                    sorted(products, key=lambda x: (x.created_at, x.id))[0] if products else None
                )
                rows.append(position_to_export_row_dict(inv, aisle, seq, p, primary))

        return CsvInventoryExporter.to_csv(rows)
