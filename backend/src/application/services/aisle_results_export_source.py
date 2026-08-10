"""Align business/summary exports with Aisle Results UI (``AislePositionsPage``).

The UI loads positions via ``ListAislePositionsUseCase`` with ``consolidate_by_sku=False``
and computes totals via ``computeResultsKpi`` / ``isExcludedFromCountedTotals``:
only ``reviewStatus === 'INVALID'`` (backend ``deleted`` position status) is excluded
from counted quantity; traceability-invalid rows remain in totals.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from src.application.mappers.position_canonical_view import build_position_canonical_view
from src.application.services.export_quantity_rollup import (
    ExportQuantityRollupConfig,
    ExportQuantityRollupService,
)
from src.domain.positions.entities import Position, PositionStatus
from src.domain.products.entities import ProductRecord

# Matches AislePositionsPage list query (photo_sequence, no SKU merge).
AISLE_RESULTS_UI_CONSOLIDATE_BY_SKU = False

# Matches frontend ``isExcludedFromCountedTotals`` (only deleted → INVALID review).
UI_ALIGNED_ROLLUP_CONFIG = ExportQuantityRollupConfig(
    exclude_traceability_invalid_from_totals=False,
)


def ui_aligned_rollup_service() -> ExportQuantityRollupService:
    return ExportQuantityRollupService(UI_ALIGNED_ROLLUP_CONFIG)


def ui_counted_totals_from_aisle_result_rows(
    positions: Sequence[Position],
    products_per_position: Sequence[Sequence[ProductRecord]],
) -> tuple[int, int]:
    """Return (total contabilizado, ítems contados) using ProductRecord cardinality.

    When a position has ProductRecords, each product is one counted item (multi-label).
    When a position has none (legacy summary-only rows), count the Position once from
    its canonical view — matching pre-D1 aisle results.
    Deleted positions are excluded.
    """
    total_qty = 0
    items = 0
    if len(positions) != len(products_per_position):
        raise ValueError("positions and products_per_position length mismatch")
    for pos, products in zip(positions, products_per_position):
        if pos.status == PositionStatus.DELETED:
            continue
        if products:
            for product in products:
                corrected = product.corrected_quantity
                view = build_position_canonical_view(pos, product, corrected_quantity=corrected)
                total_qty += view.quantity.final_display_quantity
                items += 1
            continue
        view = build_position_canonical_view(pos, None, corrected_quantity=None)
        total_qty += view.quantity.final_display_quantity
        items += 1
    return total_qty, items


def ui_counted_totals_from_primary_products(
    positions: Sequence[Position],
    primary_products: Sequence[ProductRecord | None],
) -> tuple[int, int]:
    """Legacy helper: one primary product per position (pre multi-label expansion)."""
    products_per_position: list[tuple[ProductRecord, ...]] = []
    for primary in primary_products:
        products_per_position.append((primary,) if primary is not None else ())
    return ui_counted_totals_from_aisle_result_rows(positions, products_per_position)


def operational_csv_counted_totals(rows: Sequence[Mapping[str, str]]) -> tuple[int, int]:
    """Sum ``Cantidad final`` and count rows where ``Incluido en totales`` is ``sí``."""
    total_qty = 0
    items = 0
    for row in rows:
        if (row.get("Incluido en totales") or "").strip().lower() != "sí":
            continue
        items += 1
        try:
            total_qty += int(row.get("Cantidad final") or 0)
        except (TypeError, ValueError):
            pass
    return total_qty, items
