"""Align business/summary exports with Aisle Results UI (``AislePositionsPage``).

The UI loads positions via ``ListAislePositionsUseCase`` with ``consolidate_by_sku=False``
and computes totals via ``computeResultsKpi`` / ``isExcludedFromCountedTotals``:
only ``reviewStatus === 'INVALID'`` (backend ``deleted`` position status) is excluded
from counted quantity; traceability-invalid rows remain in totals.
"""

from __future__ import annotations

from src.application.services.export_quantity_rollup import (
    ExportQuantityRollupConfig,
    ExportQuantityRollupService,
)

# Matches AislePositionsPage list query (photo_sequence, no SKU merge).
AISLE_RESULTS_UI_CONSOLIDATE_BY_SKU = False

# Matches frontend ``isExcludedFromCountedTotals`` (only deleted → INVALID review).
UI_ALIGNED_ROLLUP_CONFIG = ExportQuantityRollupConfig(
    exclude_traceability_invalid_from_totals=False,
)


def ui_aligned_rollup_service() -> ExportQuantityRollupService:
    return ExportQuantityRollupService(UI_ALIGNED_ROLLUP_CONFIG)
