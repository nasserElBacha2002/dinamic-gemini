from __future__ import annotations

from datetime import datetime, timezone

from src.application.mappers.inventory_export_rows import _field_sort_key, export_position_sort_key
from src.domain.positions.entities import Position, PositionStatus

NOW = datetime(2026, 3, 31, 12, 0, 0, tzinfo=timezone.utc)


def _position(
    position_id: str,
    *,
    pallet_id: object | None = None,
    position_barcode: object | None = None,
    entity_uid: object | None = None,
    internal_code: object | None = None,
) -> Position:
    summary: dict[str, object] = {}
    if pallet_id is not None:
        summary["pallet_id"] = pallet_id
    if position_barcode is not None:
        summary["position_barcode"] = position_barcode
    if entity_uid is not None:
        summary["entity_uid"] = entity_uid
    if internal_code is not None:
        summary["internal_code"] = internal_code
    return Position(
        id=position_id,
        aisle_id="a1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id=None,
        created_at=NOW,
        updated_at=NOW,
        detected_summary_json=summary,
    )


def test_field_sort_key_orders_numeric_values_numerically() -> None:
    values = [10, "2", 1, "0003"]
    assert sorted(values, key=_field_sort_key) == [1, "2", "0003", 10]


def test_field_sort_key_sorts_missing_values_last() -> None:
    values = [None, "", "A1", "2"]
    assert sorted(values, key=_field_sort_key) == ["2", "A1", None, ""]


def test_field_sort_key_uses_natural_text_order_for_labels() -> None:
    values = ["B2", "A10", "A1", "B10"]
    assert sorted(values, key=_field_sort_key) == ["A1", "A10", "B2", "B10"]


def test_export_position_sort_key_handles_mixed_numeric_text_and_missing_values() -> None:
    positions = [
        _position("pos-10", pallet_id="10", internal_code="SKU-10"),
        _position("pos-a1", pallet_id="A1", internal_code="SKU-A1"),
        _position("pos-2", position_barcode="2", internal_code="SKU-2"),
        _position("pos-b2", entity_uid="B2", internal_code="SKU-B2"),
        _position("pos-missing", internal_code=None),
    ]

    ordered = sorted(positions, key=export_position_sort_key)

    assert [p.id for p in ordered] == [
        "pos-2",
        "pos-10",
        "pos-a1",
        "pos-b2",
        "pos-missing",
    ]
