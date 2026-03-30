"""Sprint 2: nested ``product`` / ``quantity`` / ``traceability`` blocks on ``PositionSummaryResponse``."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from src.api.routes.v3.shared import position_to_summary
from src.domain.positions.entities import Position, PositionStatus
from src.domain.products.entities import ProductRecord


def _now() -> datetime:
    return datetime.now(timezone.utc)


def test_product_block_primary_sku_and_identity() -> None:
    now = _now()
    p = Position(
        id="p1",
        aisle_id="a1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="ev1",
        created_at=now,
        updated_at=now,
        detected_summary_json={"internal_code": "WRONG", "final_quantity": 99},
    )
    primary = ProductRecord(
        id="pr1",
        position_id="p1",
        sku="RIGHT",
        description="Label from record",
        detected_quantity=3,
        confidence=0.9,
        created_at=now,
        updated_at=now,
        corrected_quantity=None,
        qty_source="detected",
        qty_inference_reason=None,
        raw_qty=3,
        qty_parse_status="valid_positive",
    )
    r = position_to_summary(p, primary_product=primary, corrected_quantity=None)
    assert r.product.sku == "RIGHT"
    assert r.product.identity_source == "primary_product"
    assert r.product.id == "pr1"
    assert r.product.display_label == "Label from record"
    assert r.sku == r.product.sku


def test_product_block_unknown_sentinel() -> None:
    now = _now()
    p = Position(
        id="p2",
        aisle_id="a1",
        status=PositionStatus.DETECTED,
        confidence=0.5,
        needs_review=True,
        primary_evidence_id=None,
        created_at=now,
        updated_at=now,
        detected_summary_json={"internal_code": "X", "final_quantity": 1},
    )
    primary = ProductRecord(
        id="pr2",
        position_id="p2",
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
    r = position_to_summary(p, primary_product=primary)
    assert r.product.sku == "UNKNOWN"


def test_product_block_legacy_no_primary() -> None:
    now = _now()
    p = Position(
        id="p3",
        aisle_id="a1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="ev",
        created_at=now,
        updated_at=now,
        detected_summary_json={"internal_code": "LEG", "final_quantity": 4, "count_status": "COUNTED"},
    )
    r = position_to_summary(p, primary_product=None)
    assert r.product.identity_source == "summary_technical"
    assert r.product.sku == "LEG"
    assert r.product.id is None


def test_product_block_aggregated() -> None:
    now = _now()
    p = Position(
        id="p4",
        aisle_id="a1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="ev",
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "internal_code": "AGG",
            "final_quantity": 9,
            "aggregated_from_ids": ["x", "y"],
        },
    )
    primary = ProductRecord(
        id="pr4",
        position_id="p4",
        sku="IGNORED-FOR-SKU",
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
    r = position_to_summary(p, primary_product=primary)
    assert r.product.identity_source == "summary_aggregated"
    assert r.product.sku == "AGG"
    assert r.quantity.source == "consolidated"
    assert r.quantity.final == 9


def test_quantity_final_vs_qty_when_corrected() -> None:
    now = _now()
    p = Position(
        id="p5",
        aisle_id="a1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="ev",
        created_at=now,
        updated_at=now,
        detected_summary_json={"internal_code": "S", "final_quantity": 100},
    )
    primary = ProductRecord(
        id="pr5",
        position_id="p5",
        sku="S",
        description="",
        detected_quantity=2,
        confidence=0.9,
        created_at=now,
        updated_at=now,
        corrected_quantity=7,
        qty_source="detected",
        qty_inference_reason=None,
        raw_qty=2,
        qty_parse_status="valid_positive",
    )
    r = position_to_summary(p, corrected_quantity=7, primary_product=primary)
    assert r.qty == 2
    assert r.quantity.final == 7
    assert r.quantity.corrected == 7
    assert r.quantity.detected == 2
    assert r.qtySource == r.quantity.source


def test_traceability_block_matches_legacy_and_enrichment() -> None:
    now = _now()
    p = Position(
        id="p6",
        aisle_id="a1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="pe-1",
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "internal_code": "T",
            "final_quantity": 1,
            "entity_uid": "job-x_ent-1",
        },
    )
    with patch(
        "src.application.mappers.position_canonical_view.enrich_position_traceability_from_report",
        return_value=("sid-1", "valid", "f.jpg"),
    ):
        r = position_to_summary(p, primary_product=None)
    assert r.traceability.source_image_id == "sid-1"
    assert r.traceability.status == "valid"
    assert r.traceability.primary_evidence_id == "pe-1"
    assert r.traceability.has_evidence is True
    assert r.source_image_id == r.traceability.source_image_id
    assert r.traceability_status == r.traceability.status
    assert r.primary_evidence_id == r.traceability.primary_evidence_id


def test_display_label_falls_back_to_review_display_label() -> None:
    now = _now()
    p = Position(
        id="p7",
        aisle_id="a1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id=None,
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "internal_code": "C",
            "final_quantity": 1,
            "review_display_label": "  Shelf tag  ",
        },
    )
    primary = ProductRecord(
        id="pr7",
        position_id="p7",
        sku="C",
        description="   ",
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
    r = position_to_summary(p, primary_product=primary)
    assert r.product.display_label == "Shelf tag"


def test_barcode_from_snapshot() -> None:
    now = _now()
    p = Position(
        id="p8",
        aisle_id="a1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id=None,
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "internal_code": "C",
            "final_quantity": 1,
            "position_barcode": " 1234567890123 ",
        },
    )
    r = position_to_summary(p, primary_product=None)
    assert r.product.barcode == "1234567890123"
