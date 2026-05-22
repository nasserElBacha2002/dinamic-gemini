"""ExportQuantityRollupService — centralized totals and eligibility."""

from __future__ import annotations

from src.application.services.export_quantity_rollup import (
    ExportQuantityRollupConfig,
    ExportQuantityRollupService,
    ExportRollupRowInput,
)
from src.domain.positions.entities import PositionStatus
from src.domain.traceability import TraceabilityStatus


def _row(**kwargs) -> ExportRollupRowInput:
    base = dict(
        position_id="p1",
        aisle_id="a1",
        position_status=PositionStatus.DETECTED.value,
        traceability_status=TraceabilityStatus.VALID.value,
        needs_review=False,
        final_quantity=2,
    )
    base.update(kwargs)
    return ExportRollupRowInput(**base)


def test_rollup_uses_final_quantity() -> None:
    svc = ExportQuantityRollupService()
    meta = svc.rollup_row(_row(final_quantity=7))
    assert meta.included_in_totals is True
    assert meta.final_quantity_for_totals == 7


def test_corrected_quantity_reflected_via_final_quantity_field() -> None:
    svc = ExportQuantityRollupService()
    meta = svc.rollup_row(_row(final_quantity=9))
    assert meta.final_quantity_for_totals == 9


def test_deleted_row_excluded_with_reason() -> None:
    svc = ExportQuantityRollupService()
    meta = svc.rollup_row(_row(position_status=PositionStatus.DELETED.value))
    assert meta.included_in_totals is False
    assert meta.exclusion_reason == "deleted"
    assert meta.final_quantity_for_totals == 0


def test_traceability_invalid_excluded_when_config_enabled() -> None:
    svc = ExportQuantityRollupService(ExportQuantityRollupConfig(exclude_traceability_invalid_from_totals=True))
    meta = svc.rollup_row(_row(traceability_status=TraceabilityStatus.INVALID.value))
    assert meta.included_in_totals is False
    assert meta.exclusion_reason == "traceability_invalid"


def test_traceability_invalid_included_when_config_disabled() -> None:
    svc = ExportQuantityRollupService(ExportQuantityRollupConfig(exclude_traceability_invalid_from_totals=False))
    meta = svc.rollup_row(_row(traceability_status=TraceabilityStatus.INVALID.value, final_quantity=3))
    assert meta.included_in_totals is True
    assert meta.final_quantity_for_totals == 3


def test_aisle_and_inventory_totals() -> None:
    svc = ExportQuantityRollupService()
    rows = [
        _row(position_id="p1", final_quantity=2),
        _row(position_id="p2", traceability_status=TraceabilityStatus.INVALID.value, final_quantity=5),
        _row(position_id="p3", aisle_id="a2", final_quantity=4),
    ]
    inv = svc.rollup_inventory(["a1", "a2"], rows)
    assert inv.total_positions == 3
    assert inv.total_counted_quantity == 11
    assert inv.aisle_totals[0].total_counted_quantity == 7
    assert inv.aisle_totals[0].invalid_positions == 0
    assert inv.aisle_totals[1].total_counted_quantity == 4
