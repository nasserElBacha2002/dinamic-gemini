"""Épica 7: position summary mapping — sku and detected_quantity in list response."""

from datetime import datetime, timezone

import pytest

from src.api.routes.v3.shared import (
    position_to_summary as _position_to_summary,
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
    assert qty == 0


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
    assert resp.qty == 10
    assert resp.qtySource == "detected"
    assert resp.qtyInferenceReason is None
    assert resp.id == "pos-4"
    assert resp.confidence == 0.92
    assert resp.has_evidence is True
    assert resp.source_image_original_filename is None


def test_position_to_summary_has_evidence_false_when_no_primary_evidence() -> None:
    """Epic 2: has_evidence is False when primary_evidence_id is None or empty."""
    now = datetime.now(timezone.utc)
    p = Position(
        id="pos-no-ev",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.5,
        needs_review=True,
        primary_evidence_id=None,
        created_at=now,
        updated_at=now,
        detected_summary_json={"internal_code": "X", "final_quantity": 0},
    )
    resp = _position_to_summary(p)
    assert resp.has_evidence is False


def test_position_to_summary_includes_source_image_original_filename_when_in_summary() -> None:
    """Epic 2: source_image_original_filename is set from detected_summary_json when present."""
    now = datetime.now(timezone.utc)
    p = Position(
        id="pos-img",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="ev-1",
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "internal_code": "SKU",
            "final_quantity": 1,
            "source_image_id": "img-uuid",
            "source_image_original_filename": "photo.jpg",
        },
    )
    resp = _position_to_summary(p)
    assert resp.source_image_original_filename == "photo.jpg"
    assert resp.source_image_id == "img-uuid"


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
    """Negative or invalid quantity yields 0 (business rule: always show a count)."""
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
    assert qty_neg == 0

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
    assert qty_invalid == 0


def test_summary_sku_fallback_to_review_display_label_when_internal_code_null() -> None:
    """When internal_code is null, sku falls back to review_display_label (list API display)."""
    now = datetime.now(timezone.utc)
    p = Position(
        id="pos-f1",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.8,
        needs_review=True,
        primary_evidence_id=None,
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "internal_code": None,
            "review_display_label": "P-001",
            "position_barcode": "BC-001",
            "final_quantity": None,
            "product_label_quantity": 2,
        },
    )
    sku, qty = _summary_sku_and_quantity_from_position(p)
    assert sku == "P-001"
    assert qty == 2


def test_summary_sku_fallback_to_position_barcode_when_internal_code_and_rdl_null() -> None:
    """When internal_code and review_display_label are null, sku falls back to position_barcode."""
    now = datetime.now(timezone.utc)
    p = Position(
        id="pos-f2",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.7,
        needs_review=True,
        primary_evidence_id=None,
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "internal_code": None,
            "review_display_label": None,
            "position_barcode": "PALLET-42",
            "final_quantity": None,
            "product_label_quantity": None,
        },
    )
    sku, qty = _summary_sku_and_quantity_from_position(p)
    assert sku == "PALLET-42"
    assert qty == 0  # no quantity in summary → always show 0


def test_summary_sku_null_when_all_display_fields_missing() -> None:
    """When internal_code, review_display_label, and position_barcode are null/empty, sku is None. Quantity always 0."""
    now = datetime.now(timezone.utc)
    p = Position(
        id="pos-f3",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.0,
        needs_review=True,
        primary_evidence_id=None,
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "internal_code": None,
            "review_display_label": None,
            "position_barcode": None,
            "final_quantity": None,
            "product_label_quantity": None,
            "count_status": "NEEDS_REVIEW",
        },
    )
    sku, qty = _summary_sku_and_quantity_from_position(p)
    assert sku is None
    assert qty == 0  # no quantity in summary → always show 0


def test_summary_sku_prefers_internal_code_over_fallbacks() -> None:
    """internal_code takes precedence when present; fallbacks are not used."""
    now = datetime.now(timezone.utc)
    p = Position(
        id="pos-f4",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="ev-1",
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "internal_code": "SKU-REAL",
            "review_display_label": "P-001",
            "position_barcode": "BC-001",
            "final_quantity": 1,
        },
    )
    sku, qty = _summary_sku_and_quantity_from_position(p)
    assert sku == "SKU-REAL"
    assert qty == 1


def test_summary_sku_fallback_to_pallet_id_when_other_display_fields_null() -> None:
    """When internal_code, review_display_label, position_barcode are null, sku falls back to pallet_id (existing positions)."""
    now = datetime.now(timezone.utc)
    p = Position(
        id="pos-f5",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.96,
        needs_review=True,
        primary_evidence_id="ev-1",
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "entity_uid": "job_E7",
            "pallet_id": "1295612",
            "internal_code": None,
            "final_quantity": None,
            "product_label_quantity": None,
            "count_status": "NEEDS_REVIEW",
        },
    )
    sku, qty = _summary_sku_and_quantity_from_position(p)
    assert sku == "1295612"
    assert qty == 0  # no quantity in summary → always show 0


def test_position_to_summary_non_dict_detected_summary_json_no_raise() -> None:
    """Epic 2 hardening: _position_to_summary treats non-dict detected_summary_json as {} (no runtime failure)."""
    now = datetime.now(timezone.utc)
    for bad_value in (None, [], "string", 1):
        p = Position(
            id="pos-bad",
            aisle_id="aisle-1",
            status=PositionStatus.DETECTED,
            confidence=0.5,
            needs_review=True,
            primary_evidence_id=None,
            created_at=now,
            updated_at=now,
            detected_summary_json=bad_value,
        )
        resp = _position_to_summary(p)
        assert isinstance(resp, PositionSummaryResponse)
        assert resp.id == "pos-bad"
        assert resp.sku is None
        assert resp.detected_quantity == 0
        assert resp.qty == 0
        assert resp.qtySource == "detected"
        assert resp.qtyInferenceReason is None
        assert resp.has_evidence is False
        assert resp.source_image_original_filename is None
        assert resp.source_image_id is None


def test_position_to_summary_infers_qty_one_for_counted_with_evidence_missing_qty() -> None:
    """v3.2.2: has_evidence + COUNTED but qty missing -> qty=1 inferred (legacy rows)."""
    now = datetime.now(timezone.utc)
    p = Position(
        id="pos-inf",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="ev-1",
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "entity_type": "PALLET",
            "count_status": "COUNTED",
            "final_quantity": None,
            "product_label_quantity": None,
            "internal_code": "SKU-1",
        },
    )
    resp = _position_to_summary(p)
    assert resp.qty == 1
    assert resp.qtySource == "inferred"
    assert resp.qtyInferenceReason == "valid_evidence_without_explicit_quantity"
