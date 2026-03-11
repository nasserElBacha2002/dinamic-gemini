"""Épica 7: position summary mapping — sku and detected_quantity in list response."""

from datetime import datetime, timezone

import pytest

from src.api.routes.inventories_v3 import (
    _position_to_summary,
    _summary_sku_and_quantity_from_position,
)
from src.api.schemas.position_schemas import PositionSummaryResponse
from src.domain.positions.entities import Position, PositionStatus


def test_summary_sku_and_quantity_from_detected_summary() -> None:
    """Derivation returns sku and quantity when detected_summary_json is populated."""
    now = datetime.now(timezone.utc)
    p = Position(
        id="pos-1",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="ev-1",
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "internal_code": "SKU-001",
            "final_quantity": 5,
            "product_label_quantity": 5,
        },
    )
    sku, qty = _summary_sku_and_quantity_from_position(p)
    assert sku == "SKU-001"
    assert qty == 5


def test_summary_sku_and_quantity_from_product_label_quantity() -> None:
    """When final_quantity is missing, product_label_quantity is used."""
    now = datetime.now(timezone.utc)
    p = Position(
        id="pos-2",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.8,
        needs_review=True,
        primary_evidence_id=None,
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "internal_code": "X-99",
            "product_label_quantity": 3,
        },
    )
    sku, qty = _summary_sku_and_quantity_from_position(p)
    assert sku == "X-99"
    assert qty == 3


def test_summary_sku_and_quantity_empty_json_returns_none() -> None:
    """Missing or empty detected_summary_json returns None, None."""
    now = datetime.now(timezone.utc)
    p = Position(
        id="pos-3",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.0,
        needs_review=True,
        primary_evidence_id=None,
        created_at=now,
        updated_at=now,
        detected_summary_json=None,
    )
    sku, qty = _summary_sku_and_quantity_from_position(p)
    assert sku is None
    assert qty is None


def test_position_to_summary_includes_sku_and_detected_quantity() -> None:
    """_position_to_summary populates sku and detected_quantity in response."""
    now = datetime.now(timezone.utc)
    p = Position(
        id="pos-4",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.92,
        needs_review=False,
        primary_evidence_id="ev-4",
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "internal_code": "ITEM-A",
            "final_quantity": 10,
        },
    )
    resp = _position_to_summary(p)
    assert isinstance(resp, PositionSummaryResponse)
    assert resp.sku == "ITEM-A"
    assert resp.detected_quantity == 10
    assert resp.id == "pos-4"
    assert resp.confidence == 0.92


def test_summary_quantity_parses_numeric_string() -> None:
    """Quantity can be parsed from numeric string (e.g. \"12\")."""
    now = datetime.now(timezone.utc)
    p = Position(
        id="pos-5",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.0,
        needs_review=False,
        primary_evidence_id=None,
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "internal_code": "Y",
            "final_quantity": "12",
        },
    )
    sku, qty = _summary_sku_and_quantity_from_position(p)
    assert sku == "Y"
    assert qty == 12


def test_summary_quantity_rejects_negative_and_invalid() -> None:
    """Negative or invalid quantity yields None."""
    now = datetime.now(timezone.utc)
    p_neg = Position(
        id="pos-6",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.0,
        needs_review=False,
        primary_evidence_id=None,
        created_at=now,
        updated_at=now,
        detected_summary_json={"internal_code": "Z", "final_quantity": -1},
    )
    _, qty_neg = _summary_sku_and_quantity_from_position(p_neg)
    assert qty_neg is None

    p_invalid = Position(
        id="pos-7",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.0,
        needs_review=False,
        primary_evidence_id=None,
        created_at=now,
        updated_at=now,
        detected_summary_json={"internal_code": "W", "final_quantity": "not-a-number"},
    )
    _, qty_invalid = _summary_sku_and_quantity_from_position(p_invalid)
    assert qty_invalid is None
