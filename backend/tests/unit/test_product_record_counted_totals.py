"""ProductRecord cardinality for aisle counted totals."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.services.aisle_results_export_source import (
    ui_counted_totals_from_aisle_result_rows,
)
from src.domain.positions.entities import Position, PositionStatus
from src.domain.products.entities import ProductRecord

NOW = datetime(2026, 8, 10, tzinfo=timezone.utc)


def _pos(pid: str) -> Position:
    return Position(
        id=pid,
        aisle_id="a1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id=None,
        created_at=NOW,
        updated_at=NOW,
        detected_summary_json={"internal_code": "X", "final_quantity": 1},
    )


def _pr(pid: str, position_id: str, qty: int, label_id: str) -> ProductRecord:
    return ProductRecord(
        id=pid,
        position_id=position_id,
        sku=f"SKU-{pid}",
        detected_quantity=qty,
        confidence=0.9,
        created_at=NOW,
        updated_at=NOW,
        label_id=label_id,
    )


def test_multi_product_position_sums_all_quantities_and_counts_items() -> None:
    pos = _pos("p1")
    products = (
        _pr("a", "p1", 1000, "6YD0S6WVMM"),
        _pr("b", "p1", 1100, "6FYR11RPXS"),
    )
    total, items = ui_counted_totals_from_aisle_result_rows([pos], [products])
    assert items == 2
    assert total == 2100


def test_physical_fixture_five_products_total_55251() -> None:
    qtys = [10009, 1000, 1000, 1100, 42142]
    positions = [_pos(f"p{i}") for i in range(5)]
    products = [(_pr(f"pr{i}", f"p{i}", q, f"L{i}"),) for i, q in enumerate(qtys)]
    total, items = ui_counted_totals_from_aisle_result_rows(positions, products)
    assert items == 5
    assert total == 55251
