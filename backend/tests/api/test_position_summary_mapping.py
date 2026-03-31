"""Épica 7: position summary mapping — sku and detected_quantity in list response. v3.2.2: authoritative ProductRecord for qty."""

from datetime import datetime, timezone

import pytest

from src.api.routes.v3.shared import (
    position_to_summary as _position_to_summary,
    technical_snapshot_from_view,
)
from src.application.mappers.position_canonical_view import build_position_canonical_view
from src.application.mappers.position_canonical_view import summary_sku_and_quantity_from_position
from src.api.schemas.position_schemas import PositionSummaryResponse
from src.domain.positions.entities import Position, PositionStatus
from src.domain.products.entities import ProductRecord


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
    sku, qty = summary_sku_and_quantity_from_position(p)
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
    sku, qty = summary_sku_and_quantity_from_position(p)
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
    sku, qty = summary_sku_and_quantity_from_position(p)
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
    sku, qty = summary_sku_and_quantity_from_position(p)
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
    _, qty_neg = summary_sku_and_quantity_from_position(p_neg)
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
    _, qty_invalid = summary_sku_and_quantity_from_position(p_invalid)
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
    sku, qty = summary_sku_and_quantity_from_position(p)
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
    sku, qty = summary_sku_and_quantity_from_position(p)
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
    sku, qty = summary_sku_and_quantity_from_position(p)
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
    sku, qty = summary_sku_and_quantity_from_position(p)
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
    sku, qty = summary_sku_and_quantity_from_position(p)
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


def test_position_to_summary_omits_legacy_snapshot_when_include_technical_false() -> None:
    now = datetime.now(timezone.utc)
    p = Position(
        id="pos-s3-list",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id=None,
        created_at=now,
        updated_at=now,
        detected_summary_json={"entity_uid": "job_s3_E1", "internal_code": "SKU-S3", "final_quantity": 2},
    )
    resp = _position_to_summary(p, include_technical_snapshot=False)
    assert resp.detected_summary_json is None


def test_technical_snapshot_from_view_extracts_debug_fields() -> None:
    now = datetime.now(timezone.utc)
    p = Position(
        id="pos-s3-detail",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id=None,
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "entity_uid": "job_s3_E2",
            "internal_code": "SKU-S3",
            "review_display_label": "Tech label",
            "position_barcode": "BC-S3",
            "raw_qty": "4x",
            "qty_parse_status": "invalid",
            "qty_origin_field": "product_label_quantity",
            "aggregated_from_ids": ["p1", "p2"],
            "_audit": {"explicit_quantity_missing": True},
        },
    )
    view = build_position_canonical_view(p)
    snapshot = technical_snapshot_from_view(view)
    assert snapshot is not None
    assert snapshot.entity_uid == "job_s3_E2"
    assert snapshot.internal_code == "SKU-S3"
    assert snapshot.review_display_label == "Tech label"
    assert snapshot.position_barcode == "BC-S3"
    assert snapshot.raw_qty == "4x"
    assert snapshot.qty_parse_status == "invalid"
    assert snapshot.qty_origin_field == "product_label_quantity"
    assert snapshot.aggregated_from_ids == ["p1", "p2"]
    assert snapshot.audit == {"explicit_quantity_missing": True}


def test_position_to_summary_infers_qty_one_for_counted_with_evidence_missing_qty() -> None:
    """v3.2.2: has_evidence + COUNTED but qty missing -> qty=1 inferred (legacy path when no primary_product)."""
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


def test_position_to_summary_infers_one_for_needs_review_with_strong_presence_legacy() -> None:
    """NEEDS_REVIEW + strong evidence/identity/traceability -> qty=1 inferred in legacy path."""
    now = datetime.now(timezone.utc)
    p = Position(
        id="pos-nr-strong",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=True,
        primary_evidence_id="ev-1",
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "entity_type": "PALLET",
            "count_status": "NEEDS_REVIEW",
            "final_quantity": None,
            "product_label_quantity": None,
            "internal_code": "SKU-STRONG",
            "traceability_status": "valid",
        },
    )
    resp = _position_to_summary(p)
    assert resp.qty == 1
    assert resp.qtySource == "inferred"
    assert resp.qtyInferenceReason == "valid_evidence_without_explicit_quantity"
    assert resp.qtyResolved is True


def test_position_to_summary_needs_review_weak_presence_unresolved() -> None:
    """NEEDS_REVIEW with weak presence/evidence does not infer qty=1."""
    now = datetime.now(timezone.utc)
    p = Position(
        id="pos-nr-weak",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.6,
        needs_review=True,
        primary_evidence_id=None,
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "entity_type": "PALLET",
            "count_status": "NEEDS_REVIEW",
            "final_quantity": None,
            "product_label_quantity": None,
            # No identity, no traceability_status, and no primary_evidence_id.
        },
    )
    resp = _position_to_summary(p)
    assert resp.qty == 0
    assert resp.qtySource == "detected"
    assert resp.qtyResolved is False


def test_position_to_summary_includes_corrected_quantity_when_provided() -> None:
    """v3.2.5 Phase 2: When corrected_quantity is passed (e.g. from display primary product), response includes it."""
    now = datetime.now(timezone.utc)
    p = Position(
        id="pos-cq",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="ev-1",
        created_at=now,
        updated_at=now,
        detected_summary_json={"internal_code": "SKU-X", "final_quantity": 3},
    )
    primary = ProductRecord(
        id="prod-cq",
        position_id="pos-cq",
        sku="SKU-X",
        description="",
        detected_quantity=3,
        confidence=0.9,
        created_at=now,
        updated_at=now,
        corrected_quantity=7,
        qty_source="detected",
        qty_inference_reason=None,
        raw_qty=3,
        qty_parse_status="valid_positive",
    )
    resp = _position_to_summary(p, corrected_quantity=7, primary_product=primary)
    assert resp.corrected_quantity == 7


def test_position_to_summary_corrected_quantity_none_when_not_provided() -> None:
    """v3.2.5 Phase 2: When corrected_quantity is not passed (or primary has None), response has corrected_quantity None."""
    now = datetime.now(timezone.utc)
    p = Position(
        id="pos-no-cq",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="ev-1",
        created_at=now,
        updated_at=now,
        detected_summary_json={"internal_code": "SKU-Y", "final_quantity": 2},
    )
    primary = ProductRecord(
        id="prod-no-cq",
        position_id="pos-no-cq",
        sku="SKU-Y",
        description="",
        detected_quantity=2,
        confidence=0.9,
        created_at=now,
        updated_at=now,
        corrected_quantity=None,
        qty_source="detected",
        qty_inference_reason=None,
        raw_qty=2,
        qty_parse_status="valid_positive",
    )
    resp = _position_to_summary(p, primary_product=primary)
    assert resp.corrected_quantity is None


def test_position_to_summary_uses_primary_product_authoritative() -> None:
    """v3.2.2: When primary_product is provided with qty_source set, API uses it as authoritative (not detected_summary_json)."""
    now = datetime.now(timezone.utc)
    p = Position(
        id="pos-auth",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.85,
        needs_review=False,
        primary_evidence_id="ev-1",
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "internal_code": "SKU-OLD",
            "final_quantity": 99,
        },
    )
    primary = ProductRecord(
        id="prod-1",
        position_id="pos-auth",
        sku="SKU-A",
        description="",
        detected_quantity=5,
        confidence=0.9,
        created_at=now,
        updated_at=now,
        corrected_quantity=None,
        qty_source="detected",
        qty_inference_reason=None,
        raw_qty=5,
        qty_parse_status="valid_positive",
    )
    resp = _position_to_summary(p, primary_product=primary)
    assert resp.qty == 5
    assert resp.qtySource == "detected"
    assert resp.qtyInferenceReason is None
    assert resp.qtyResolved is True


def test_position_to_summary_primary_product_empty_qty_source_uses_persisted_qty() -> None:
    """v3.2.2 corrective: When primary_product exists but qty_source is empty (legacy row), use ProductRecord.detected_quantity so qty never diverges; qtyResolved is None."""
    now = datetime.now(timezone.utc)
    p = Position(
        id="pos-legacy",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.8,
        needs_review=False,
        primary_evidence_id="ev-1",
        created_at=now,
        updated_at=now,
        detected_summary_json={"internal_code": "SKU-OLD", "final_quantity": 99},
    )
    primary = ProductRecord(
        id="prod-legacy",
        position_id="pos-legacy",
        sku="SKU-A",
        description="",
        detected_quantity=3,
        confidence=0.8,
        created_at=now,
        updated_at=now,
        corrected_quantity=None,
        qty_source="",
        qty_inference_reason=None,
        raw_qty=3,
        qty_parse_status="valid_positive",
    )
    resp = _position_to_summary(p, primary_product=primary)
    assert resp.qty == 3
    assert resp.qtySource == "detected"
    assert resp.qtyInferenceReason is None
    assert resp.qtyResolved is None


def test_position_to_summary_unresolved_primary_returns_zero_detected() -> None:
    """v3.2.2: primary_product with qty_source=unresolved yields (0, 'detected', None) so UI can treat as non-valid visible."""
    now = datetime.now(timezone.utc)
    p = Position(
        id="pos-unr",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.5,
        needs_review=True,
        primary_evidence_id=None,
        created_at=now,
        updated_at=now,
        detected_summary_json={},
    )
    primary = ProductRecord(
        id="prod-unr",
        position_id="pos-unr",
        sku="X",
        description="",
        detected_quantity=0,
        confidence=0.5,
        created_at=now,
        updated_at=now,
        corrected_quantity=None,
        qty_source="unresolved",
        qty_inference_reason=None,
        raw_qty=None,
        qty_parse_status="missing",
    )
    resp = _position_to_summary(p, primary_product=primary)
    assert resp.qty == 0
    assert resp.qtySource == "detected"
    assert resp.qtyInferenceReason is None
    assert resp.qtyResolved is False


def test_position_to_summary_legacy_fallback_when_no_primary_product() -> None:
    """v3.2.2: When primary_product is None, qty contract is built from detected_summary_json (legacy)."""
    now = datetime.now(timezone.utc)
    p = Position(
        id="pos-leg",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="ev-1",
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "internal_code": "SKU",
            "final_quantity": 7,
            "count_status": "COUNTED",
        },
    )
    resp = _position_to_summary(p, primary_product=None)
    assert resp.qty == 7
    assert resp.qtySource == "detected"
    assert resp.qtyInferenceReason is None
    assert resp.qtyResolved is True


def test_position_to_summary_legacy_with_qty_is_resolved_in_summary_returns_it() -> None:
    """When legacy path uses pre-populated qty_final/qty_source from summary, qtyResolved comes from qty_is_resolved when present."""
    now = datetime.now(timezone.utc)
    p = Position(
        id="pos-leg-2",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="ev-1",
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "qty_final": 0,
            "qty_source": "unresolved",
            "qty_is_resolved": False,
        },
    )
    resp = _position_to_summary(p, primary_product=None)
    assert resp.qty == 0
    assert resp.qtyResolved is False


def test_regression_valid_entity_never_exposes_unjustified_null_qty() -> None:
    """Regression: valid visible entity must not expose null qty; authoritative ProductRecord supplies explicit qty."""
    now = datetime.now(timezone.utc)
    p = Position(
        id="pos-reg",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="ev-1",
        created_at=now,
        updated_at=now,
        detected_summary_json={"internal_code": "SKU-OK", "final_quantity": None},
    )
    primary = ProductRecord(
        id="prod-reg",
        position_id="pos-reg",
        sku="SKU-OK",
        description="",
        detected_quantity=1,
        confidence=0.9,
        created_at=now,
        updated_at=now,
        corrected_quantity=None,
        qty_source="inferred",
        qty_inference_reason="valid_evidence_without_explicit_quantity",
        raw_qty=None,
        qty_parse_status="missing",
    )
    resp = _position_to_summary(p, primary_product=primary)
    assert resp.qty == 1
    assert resp.qtySource == "inferred"
    assert resp.qtyInferenceReason is not None
    assert resp.qtyResolved is True


def test_regression_valid_entity_never_exposes_unjustified_zero() -> None:
    """Regression: when SKU was correct but qty could regress to 0 after parser changes, authoritative ProductRecord prevents unjustified 0."""
    now = datetime.now(timezone.utc)
    p = Position(
        id="pos-zero",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="ev-1",
        created_at=now,
        updated_at=now,
        detected_summary_json={"internal_code": "SKU-OK", "final_quantity": 0},
    )
    primary = ProductRecord(
        id="prod-zero",
        position_id="pos-zero",
        sku="SKU-OK",
        description="",
        detected_quantity=1,
        confidence=0.9,
        created_at=now,
        updated_at=now,
        corrected_quantity=None,
        qty_source="inferred",
        qty_inference_reason="valid_evidence_without_explicit_quantity",
        raw_qty=0,
        qty_parse_status="zero",
    )
    resp = _position_to_summary(p, primary_product=primary)
    assert resp.qty == 1
    assert resp.qtySource == "inferred"


def test_position_to_summary_consolidated_qty_uses_product_record_projection() -> None:
    """
    v3.2.3: When qty_source is 'consolidated', API should use ProductRecord.detected_quantity
    as the authoritative quantity (same behavior as detected), proving projection alignment.
    """
    now = datetime.now(timezone.utc)
    p = Position(
        id="pos-consolidated",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="ev-1",
        created_at=now,
        updated_at=now,
        detected_summary_json={"internal_code": "SKU-X", "final_quantity": 99},
    )
    primary = ProductRecord(
        id="prod-consolidated",
        position_id="pos-consolidated",
        sku="SKU-X",
        description="",
        detected_quantity=4,
        confidence=0.9,
        created_at=now,
        updated_at=now,
        corrected_quantity=None,
        qty_source="consolidated",
        qty_inference_reason=None,
        raw_qty=None,
        qty_parse_status="valid_positive",
    )
    resp = _position_to_summary(p, primary_product=primary)
    assert resp.qty == 4
    assert resp.qtySource == "consolidated"
    # Consolidated is treated as an explicit resolved quantity in the v3 contract.
    assert resp.qtyResolved is True
    # v3.2.3.E3 regression: detected_quantity must align with authoritative qty,
    # not stale detected_summary_json (99), so response does not expose pre-consolidation values.
    assert resp.detected_quantity == 4


def test_position_to_summary_aggregated_row_emits_consolidated_qty_source() -> None:
    """Phase 5 Block 1: aggregated/consolidated rows must be explicit via qtySource='consolidated'."""
    now = datetime.now(timezone.utc)
    p = Position(
        id="pos-agg-1",
        aisle_id="aisle-1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="ev-1",
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "internal_code": "SKU-AGG",
            "final_quantity": 7,
            "aggregated_from_ids": ["pos-a", "pos-b"],
        },
    )
    resp = _position_to_summary(p, primary_product=None)
    assert resp.qty == 7
    assert resp.qtySource == "consolidated"
    assert resp.qtyResolved is True
    assert resp.corrected_quantity is None
