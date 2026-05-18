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
    primary_products: Sequence[ProductRecord | None],
) -> tuple[int, int]:
    """Return (total contabilizado, ítems contados) using the same rules as the Aisle Results UI."""
    total_qty = 0
    items = 0
    if len(positions) != len(primary_products):
        raise ValueError("positions and primary_products length mismatch")
    for pos, primary in zip(positions, primary_products):
        if pos.status == PositionStatus.DELETED:
            continue
        corrected = primary.corrected_quantity if primary is not None else None
        view = build_position_canonical_view(pos, primary, corrected_quantity=corrected)
        total_qty += view.quantity.final_display_quantity
        items += 1
    return total_qty, items


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
