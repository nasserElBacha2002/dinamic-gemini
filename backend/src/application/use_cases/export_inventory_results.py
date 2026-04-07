"""
Export consolidated inventory results as CSV (v3).

Uses the same SKU consolidation as ``ListAislePositionsUseCase`` and summary mapping as
``position_to_summary`` (via ``inventory_export_rows``).

**Multi-run scope:** For each aisle, only positions in the **operational** job slice (or **legacy**
``job_id IS NULL`` when no operational pointer) are exported — same effective slice as the resolver,
not all runs. For Aisle Results, ``ExportAisleResultsCsvUseCase`` / ``GET …/aisles/{id}/export`` uses
the same row builder with an optional ``job_id`` query param (aligned with ``GET …/positions``).

**Ordering (deterministic, operator-friendly):**
There is no explicit aisle ``display_order`` on the domain model today. Aisles are ordered by
``natural_sort_key_parts(aisle.code)``, then ``aisle.created_at``, then ``aisle.id``. Exported
``aisle_sequence`` is 1-based index in that order. Within an aisle, positions use
``export_position_sort_key``: natural sort on the human-facing position code (``pallet_id`` →
``position_barcode`` → ``entity_uid``), then ``internal_code``, ``created_at``, ``id``.
``final_quantity`` is ``corrected_quantity`` when set on the primary product row, otherwise the same
``final_quantity`` as ``position_to_summary`` (detected/aggregated path).

Primary product rows use ``select_display_primary_product`` — same rule as v3 list/detail/review-queue
(earliest ``created_at``, then ``id``).
"""

from __future__ import annotations

from collections import defaultdict
from typing import DefaultDict, List, Optional

from src.application.errors import AisleNotFoundError, InventoryNotFoundError
from src.application.services.result_context_resolver import ResultContextResolver
from src.domain.aisle.entities import Aisle
from src.domain.inventory.entities import Inventory
from src.application.mappers.inventory_export_rows import (
    export_position_sort_key,
    position_to_operational_export_row_dict,
    position_to_technical_export_row_dict,
)
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    PositionRepository,
    ProductRecordRepository,
)
from src.application.services.csv_inventory_exporter import (
    CsvInventoryExporter,
    INVENTORY_RESULTS_CSV_FIELDS,
    INVENTORY_RESULTS_TECHNICAL_CSV_FIELDS,
)
from src.application.services.display_primary_product import select_display_primary_product
from src.application.services.position_sku_consolidation import consolidate_positions_by_sku
from src.application.utils.natural_sort import natural_sort_key_parts
from src.domain.positions.entities import Position, PositionStatus


def append_inventory_csv_rows_for_aisle(
    rows: List[dict],
    *,
    inv: Inventory,
    aisle: Aisle,
    aisle_sequence: int,
    resolver: ResultContextResolver,
    explicit_job_id: Optional[str],
    aisle_positions: List[Position],
    product_record_repo: ProductRecordRepository,
    technical: bool,
) -> None:
    """Append consolidated CSV row dicts for one aisle (same slice rules as ``ListAislePositions``)."""
    ctx = resolver.resolve(aisle=aisle, explicit_job_id=explicit_job_id)
    slice_job = ctx.job_id_for_slice
    candidates = [p for p in aisle_positions if p.status != PositionStatus.DELETED]
    if slice_job is None:
        raw = [p for p in candidates if p.job_id is None]
    else:
        raw = [p for p in candidates if p.job_id == slice_job]
    consolidated = consolidate_positions_by_sku(raw)
    consolidated_sorted = sorted(consolidated, key=export_position_sort_key)
    for p in consolidated_sorted:
        products = product_record_repo.list_by_position(p.id)
        primary = select_display_primary_product(products)
        if technical:
            rows.append(position_to_technical_export_row_dict(inv, aisle, aisle_sequence, p))
        else:
            rows.append(position_to_operational_export_row_dict(inv, aisle, aisle_sequence, p, primary))


class ExportInventoryResultsUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        position_repo: PositionRepository,
        product_record_repo: ProductRecordRepository,
        result_context_resolver: ResultContextResolver,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._position_repo = position_repo
        self._product_record_repo = product_record_repo
        self._resolver = result_context_resolver

    def execute_csv(self, inventory_id: str, *, technical: bool = False) -> str:
        inv = self._inventory_repo.get_by_id(inventory_id)
        if inv is None:
            raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")

        aisles = list(self._aisle_repo.list_by_inventory(inventory_id))
        sorted_aisles = sorted(
            aisles,
            key=lambda a: (natural_sort_key_parts(a.code), a.created_at, a.id),
        )
        aisle_ids = [a.id for a in sorted_aisles]
        if not aisle_ids:
            fieldnames = INVENTORY_RESULTS_TECHNICAL_CSV_FIELDS if technical else INVENTORY_RESULTS_CSV_FIELDS
            return CsvInventoryExporter.to_csv([], fieldnames=fieldnames)
        all_positions = list(self._position_repo.list_by_aisles(aisle_ids))
        by_aisle: DefaultDict[str, List[Position]] = defaultdict(list)
        for p in all_positions:
            by_aisle[p.aisle_id].append(p)

        rows: List[dict] = []
        for seq, aisle in enumerate(sorted_aisles, start=1):
            append_inventory_csv_rows_for_aisle(
                rows,
                inv=inv,
                aisle=aisle,
                aisle_sequence=seq,
                resolver=self._resolver,
                explicit_job_id=None,
                aisle_positions=list(by_aisle.get(aisle.id, [])),
                product_record_repo=self._product_record_repo,
                technical=technical,
            )

        fieldnames = INVENTORY_RESULTS_TECHNICAL_CSV_FIELDS if technical else INVENTORY_RESULTS_CSV_FIELDS
        return CsvInventoryExporter.to_csv(rows, fieldnames=fieldnames)


class ExportAisleResultsCsvUseCase:
    """CSV for a single aisle — same columns as inventory export, scoped slice as ``GET .../positions``.

    Use when exporting from Aisle Results so rows match the visible ``job_id`` (explicit run) or the
    resolver default (operational / legacy) when ``job_id`` is omitted.
    """

    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        position_repo: PositionRepository,
        product_record_repo: ProductRecordRepository,
        result_context_resolver: ResultContextResolver,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._position_repo = position_repo
        self._product_record_repo = product_record_repo
        self._resolver = result_context_resolver

    def execute_csv(
        self,
        inventory_id: str,
        aisle_id: str,
        *,
        job_id: Optional[str] = None,
        technical: bool = False,
    ) -> str:
        inv = self._inventory_repo.get_by_id(inventory_id)
        if inv is None:
            raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")
        aisle = self._aisle_repo.get_by_id(aisle_id)
        if aisle is None or aisle.inventory_id != inventory_id:
            raise AisleNotFoundError(
                f"Aisle {aisle_id} not found or does not belong to inventory {inventory_id}"
            )
        jid = str(job_id).strip() if job_id and str(job_id).strip() else None
        aisle_positions = list(self._position_repo.list_by_aisles([aisle_id]))
        rows: List[dict] = []
        append_inventory_csv_rows_for_aisle(
            rows,
            inv=inv,
            aisle=aisle,
            aisle_sequence=1,
            resolver=self._resolver,
            explicit_job_id=jid,
            aisle_positions=aisle_positions,
            product_record_repo=self._product_record_repo,
            technical=technical,
        )
        fieldnames = INVENTORY_RESULTS_TECHNICAL_CSV_FIELDS if technical else INVENTORY_RESULTS_CSV_FIELDS
        return CsvInventoryExporter.to_csv(rows, fieldnames=fieldnames)
