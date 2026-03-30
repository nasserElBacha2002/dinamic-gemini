"""Parity tests for :mod:`src.application.mappers.position_canonical_view` (Sprint 1 / ticket 1.4).

Covers primary vs summary, aggregated rows, UNKNOWN SKU, legacy divergence, traceability,
and alignment with :func:`src.api.routes.v3.shared.position_to_summary` where useful.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from src.application.mappers.position_canonical_view import build_position_canonical_view
from src.application.services.position_traceability import reset_traceability_cache_for_tests
from src.domain.positions.entities import Position, PositionStatus
from src.domain.products.entities import ProductRecord


@pytest.fixture(autouse=True)
def _clear_traceability_cache() -> None:
    reset_traceability_cache_for_tests()
    yield
    reset_traceability_cache_for_tests()


def _pos(**kwargs: object) -> Position:
    now = datetime.now(timezone.utc)
    defaults: dict = {
        "id": "pos-1",
        "aisle_id": "aisle-1",
        "status": PositionStatus.DETECTED,
        "confidence": 0.9,
        "needs_review": False,
        "primary_evidence_id": "ev-1",
        "created_at": now,
        "updated_at": now,
        "detected_summary_json": {},
    }
    defaults.update(kwargs)
    return Position(**defaults)  # type: ignore[arg-type]


def test_primary_product_sku_wins_over_divergent_summary_internal_code() -> None:
    now = datetime.now(timezone.utc)
    p = _pos(
        id="pos-sku",
        detected_summary_json={"internal_code": "SUMMARY-SKU", "final_quantity": 99},
    )
    primary = ProductRecord(
        id="prod-1",
        position_id="pos-sku",
        sku="RECORD-SKU",
        description="",
        detected_quantity=4,
        confidence=0.9,
        created_at=now,
        updated_at=now,
        corrected_quantity=None,
        qty_source="detected",
        qty_inference_reason=None,
        raw_qty=4,
        qty_parse_status="valid_positive",
    )
    view = build_position_canonical_view(p, primary)
    assert view.product.public_sku == "RECORD-SKU"
    assert view.product.identity_source == "primary_product"
    assert view.quantity.qty == 4
    assert view.quantity.detected_quantity == 4


def test_primary_unknown_sentinel_not_replaced_by_summary_sku() -> None:
    now = datetime.now(timezone.utc)
    p = _pos(
        detected_summary_json={"internal_code": "HAS-CODE", "final_quantity": 1},
    )
    primary = ProductRecord(
        id="prod-u",
        position_id=p.id,
        sku="UNKNOWN",
        description="",
        detected_quantity=1,
        confidence=0.5,
        created_at=now,
        updated_at=now,
        corrected_quantity=None,
        qty_source="detected",
        qty_inference_reason=None,
        raw_qty=1,
        qty_parse_status="valid_positive",
    )
    view = build_position_canonical_view(p, primary)
    assert view.product.public_sku == "UNKNOWN"


def test_primary_empty_sku_falls_back_to_summary() -> None:
    now = datetime.now(timezone.utc)
    p = _pos(
        detected_summary_json={"internal_code": "FALLBACK", "final_quantity": 2},
    )
    primary = ProductRecord(
        id="prod-e",
        position_id=p.id,
        sku="   ",
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
    view = build_position_canonical_view(p, primary)
    assert view.product.public_sku == "FALLBACK"


def test_no_primary_uses_legacy_summary_path() -> None:
    p = _pos(
        primary_evidence_id="ev-1",
        detected_summary_json={
            "internal_code": "LEG",
            "final_quantity": 7,
            "count_status": "COUNTED",
        },
    )
    view = build_position_canonical_view(p, None)
    assert view.product.identity_source == "summary_technical"
    assert view.product.public_sku == "LEG"
    assert view.quantity.qty == 7
    assert view.quantity.detected_quantity == 7


def test_aggregated_row_authority_from_summary_final_quantity() -> None:
    now = datetime.now(timezone.utc)
    p = _pos(
        id="pos-agg",
        detected_summary_json={
            "internal_code": "AGG",
            "final_quantity": 12,
            "aggregated_from_ids": ["a", "b"],
        },
    )
    primary = ProductRecord(
        id="prod-agg",
        position_id="pos-agg",
        sku="SHOULD-NOT-DRIVE-QTY",
        description="",
        detected_quantity=1,
        confidence=0.9,
        created_at=now,
        updated_at=now,
        corrected_quantity=None,
        qty_source="detected",
        qty_inference_reason=None,
        raw_qty=1,
        qty_parse_status="valid_positive",
    )
    view = build_position_canonical_view(p, primary)
    assert view.quantity.is_aggregated is True
    assert view.quantity.qty == 12
    assert view.quantity.detected_quantity == 12
    assert view.quantity.qty_source == "consolidated"
    assert view.product.identity_source == "summary_aggregated"
    assert view.product.primary_product_id == primary.id


def test_qty_and_detected_quantity_aligned_for_primary_path() -> None:
    now = datetime.now(timezone.utc)
    p = _pos(detected_summary_json={"internal_code": "X", "final_quantity": 100})
    primary = ProductRecord(
        id="prod-a",
        position_id=p.id,
        sku="X",
        description="",
        detected_quantity=3,
        confidence=0.9,
        created_at=now,
        updated_at=now,
        corrected_quantity=None,
        qty_source="inferred",
        qty_inference_reason="r",
        raw_qty=3,
        qty_parse_status="valid_positive",
    )
    view = build_position_canonical_view(p, primary)
    assert view.quantity.qty == view.quantity.detected_quantity == 3


def test_legacy_structured_qty_can_differ_from_summary_literal_quantity() -> None:
    """``summary_sku_and_quantity_from_position`` reads ``final_quantity`` / label qty, not ``qty_final``."""
    p = _pos(
        primary_evidence_id=None,
        detected_summary_json={
            "internal_code": "Q",
            "qty_final": 5,
            "qty_source": "inferred",
            "qty_is_resolved": True,
        },
    )
    view = build_position_canonical_view(p, None)
    assert view.quantity.qty == 5
    assert view.quantity.qty_source == "inferred"
    assert view.quantity.detected_quantity == 0


def test_corrected_quantity_in_canonical_layer_from_parameter() -> None:
    now = datetime.now(timezone.utc)
    p = _pos()
    primary = ProductRecord(
        id="prod-c",
        position_id=p.id,
        sku="S",
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
    view = build_position_canonical_view(p, primary, corrected_quantity=9)
    assert view.quantity.corrected_quantity == 9


def test_corrected_quantity_falls_back_to_primary_when_param_none() -> None:
    now = datetime.now(timezone.utc)
    p = _pos()
    primary = ProductRecord(
        id="prod-c2",
        position_id=p.id,
        sku="S",
        description="",
        detected_quantity=2,
        confidence=0.9,
        created_at=now,
        updated_at=now,
        corrected_quantity=6,
        qty_source="detected",
        qty_inference_reason=None,
        raw_qty=2,
        qty_parse_status="valid_positive",
    )
    view = build_position_canonical_view(p, primary, corrected_quantity=None)
    assert view.quantity.corrected_quantity == 6


def test_traceability_enrichment_fills_missing_summary_fields() -> None:
    p = _pos(
        detected_summary_json={
            "entity_uid": "job-abc_ent-1",
            "internal_code": "T",
        },
    )
    with patch(
        "src.application.mappers.position_canonical_view.enrich_position_traceability_from_report",
        return_value=("src-img-99", "valid", "frame.jpg"),
    ):
        view = build_position_canonical_view(p, None)
    assert view.traceability.source_image_id == "src-img-99"
    assert view.traceability.traceability_status == "valid"
    assert view.traceability.source_image_original_filename == "frame.jpg"


def test_position_to_summary_exposes_same_flat_fields_as_canonical_view() -> None:
    """Regression: single HTTP assembly path mirrors :class:`PositionCanonicalView` (ticket 1.4)."""
    from src.api.routes.v3.shared import position_to_summary

    now = datetime.now(timezone.utc)
    p = _pos(
        detected_summary_json={
            "internal_code": "API-PARITY",
            "final_quantity": 50,
            "source_image_id": "img-self",
            "traceability_status": "valid",
        },
    )
    primary = ProductRecord(
        id="prod-p",
        position_id=p.id,
        sku="FROM-RECORD",
        description="",
        detected_quantity=2,
        confidence=0.9,
        created_at=now,
        updated_at=now,
        corrected_quantity=8,
        qty_source="detected",
        qty_inference_reason=None,
        raw_qty=2,
        qty_parse_status="valid_positive",
    )
    view = build_position_canonical_view(
        p,
        primary,
        corrected_quantity=primary.corrected_quantity,
    )
    resp = position_to_summary(
        p,
        corrected_quantity=primary.corrected_quantity,
        primary_product=primary,
    )
    assert resp.sku == view.product.public_sku
    assert resp.qty == view.quantity.qty
    assert resp.qtySource == view.quantity.qty_source
    assert resp.qtyInferenceReason == view.quantity.qty_inference_reason
    assert resp.qtyResolved == view.quantity.qty_resolved
    assert resp.detected_quantity == view.quantity.detected_quantity
    assert resp.corrected_quantity == view.quantity.corrected_quantity
    assert resp.source_image_id == view.traceability.source_image_id
    assert resp.traceability_status == view.traceability.traceability_status
    assert resp.has_evidence == view.review.has_evidence
    assert resp.status == view.review.status
    assert resp.needs_review == view.review.needs_review
