"""
Stage 2.1.A — Structural & label-aware foundation.

Tests: schema v21, deterministic ordering, duplicate barcode conflict,
pallet_id resolution, count_status, entity_quality_score, report summary.
"""

import pytest

from src.decision.count_status import assign_count_status
from src.decision.entity_order import sort_entities_deterministically
from src.decision.pallet_id import resolve_pallet_id
from src.decision.quality_score import compute_entity_quality_score
from src.domain.entity import Entity
from src.exceptions.global_analysis_exceptions import GlobalAnalysisValidationError
from src.parsing.global_analysis_parser import parse_entities, _safe_bbox
from src.reporting.hybrid_report import build_hybrid_report, _build_summary_from_entities
from src.validation.global_analysis_schema import validate_global_analysis_structure_v21


# --- Schema validation ---

VALID_V21_PAYLOAD = {
    "total_entities_detected": 2,
    "entities": [
        {
            "entity_type": "PALLET",
            "model_entity_id": "E1",
            "position_barcode": "POS-001",
            "internal_code": "Prod A",
            "product_label_quantity": 15,
            "has_boxes": True,
            "confidence": 0.92,
        },
        {
            "entity_type": "EMPTY_PALLET",
            "model_entity_id": "E2",
            "position_barcode": None,
            "internal_code": None,
            "product_label_quantity": None,
            "has_boxes": False,
            "confidence": 0.88,
        },
    ],
}


def test_validate_v21_valid_passes():
    validate_global_analysis_structure_v21(VALID_V21_PAYLOAD)


def test_validate_v21_missing_entities_raises():
    data = {"total_entities_detected": 0}
    with pytest.raises(GlobalAnalysisValidationError, match="entities"):
        validate_global_analysis_structure_v21(data)


def test_validate_v21_total_mismatch_raises():
    data = {**VALID_V21_PAYLOAD, "total_entities_detected": 3}
    with pytest.raises(GlobalAnalysisValidationError, match="must equal"):
        validate_global_analysis_structure_v21(data)


def test_analyzer_v21_count_mismatch_normalized():
    """When Gemini returns total_entities_detected != len(entities), analyzer normalizes count and passes validation."""
    from unittest.mock import MagicMock
    import json
    import numpy as np
    from src.llm.gemini_global_analyzer import GeminiGlobalAnalyzer

    # Gemini-like mismatch: says 5 but only 4 entities
    payload = {
        "total_entities_detected": 5,
        "entities": [
            {"entity_type": "PALLET", "model_entity_id": "E1", "has_boxes": True, "confidence": 0.9},
            {"entity_type": "PALLET", "model_entity_id": "E2", "has_boxes": True, "confidence": 0.85},
            {"entity_type": "EMPTY_PALLET", "model_entity_id": "E3", "has_boxes": False, "confidence": 0.8},
            {"entity_type": "PALLET", "model_entity_id": "E4", "has_boxes": True, "confidence": 0.75},
        ],
    }
    mock_client = MagicMock()
    mock_client.generate_global_analysis_structured.return_value = json.dumps(payload)
    analyzer = GeminiGlobalAnalyzer(mock_client)
    one_frame = [np.zeros((64, 64, 3), dtype=np.uint8)]

    result = analyzer.analyze_video_frames(one_frame)

    assert result["total_entities_detected"] == 4
    assert len(result["entities"]) == 4


def test_validate_v21_entity_type_invalid_raises():
    data = {
        "total_entities_detected": 1,
        "entities": [
            {
                "entity_type": "UNKNOWN",
                "model_entity_id": "E1",
                "has_boxes": False,
                "confidence": 0.9,
            },
        ],
    }
    with pytest.raises(GlobalAnalysisValidationError, match="entity_type"):
        validate_global_analysis_structure_v21(data)


def test_validate_v21_duplicate_model_entity_id_raises():
    data = {
        "total_entities_detected": 2,
        "entities": [
            {"entity_type": "PALLET", "model_entity_id": "E1", "has_boxes": False, "confidence": 0.9},
            {"entity_type": "PALLET", "model_entity_id": "E1", "has_boxes": False, "confidence": 0.8},
        ],
    }
    with pytest.raises(GlobalAnalysisValidationError, match="Duplicate model_entity_id"):
        validate_global_analysis_structure_v21(data)


def test_validate_v21_confidence_out_of_range_raises():
    data = {
        "total_entities_detected": 1,
        "entities": [
            {"entity_type": "PALLET", "model_entity_id": "E1", "has_boxes": False, "confidence": 1.5},
        ],
    }
    with pytest.raises(GlobalAnalysisValidationError, match="0, 1"):
        validate_global_analysis_structure_v21(data)


def test_validate_v21_bbox_out_of_range_raises():
    data = {
        "total_entities_detected": 1,
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "has_boxes": False,
                "confidence": 0.9,
                "position_label_bbox": [0.1, 0.2, 1.5, 0.4],
            },
        ],
    }
    with pytest.raises(GlobalAnalysisValidationError, match="0, 1"):
        validate_global_analysis_structure_v21(data)


def test_validate_v21_bbox_invalid_order_raises():
    data = {
        "total_entities_detected": 1,
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "has_boxes": False,
                "confidence": 0.9,
                "position_label_bbox": [0.5, 0.2, 0.3, 0.4],
            },
        ],
    }
    with pytest.raises(GlobalAnalysisValidationError, match="x1 < x2"):
        validate_global_analysis_structure_v21(data)


def test_validate_v21_bbox_y1_ge_y2_raises():
    data = {
        "total_entities_detected": 1,
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "has_boxes": False,
                "confidence": 0.9,
                "product_label_bbox": [0.1, 0.5, 0.3, 0.2],
            },
        ],
    }
    with pytest.raises(GlobalAnalysisValidationError, match="y1 < y2"):
        validate_global_analysis_structure_v21(data)


# --- Parse entities ---

def test_parse_entities_sets_entity_uid_and_original_index():
    entities = parse_entities(VALID_V21_PAYLOAD, job_id="job123")
    assert len(entities) == 2
    assert entities[0].entity_uid == "job123_E1"
    assert entities[0].original_index == 0
    assert entities[1].entity_uid == "job123_E2"
    assert entities[1].original_index == 1
    assert entities[0].entity_type == "PALLET"
    assert entities[1].entity_type == "EMPTY_PALLET"


def test_parse_entities_bbox_preserves_float_precision():
    """Bbox parsing must preserve floats (e.g. 0.42 stays 0.42, not 0)."""
    payload = {
        "total_entities_detected": 1,
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "has_boxes": False,
                "confidence": 0.9,
                "position_label_bbox": [0.42, 0.1, 0.58, 0.25],
                "product_label_bbox": [0.0, 0.0, 0.2, 0.15],
            },
        ],
    }
    entities = parse_entities(payload, job_id="j")
    assert entities[0].position_label_bbox == [0.42, 0.1, 0.58, 0.25]
    assert entities[0].product_label_bbox == [0.0, 0.0, 0.2, 0.15]
    assert all(isinstance(x, float) for x in (entities[0].position_label_bbox or []))


def test_safe_bbox_preserves_floats():
    assert _safe_bbox([0.42, 0.1, 0.58, 0.25]) == [0.42, 0.1, 0.58, 0.25]
    assert _safe_bbox([1, 0, 1, 1]) == [1.0, 0.0, 1.0, 1.0]
    assert _safe_bbox(None) is None


# --- Deterministic ordering ---

def test_sort_entities_deterministically_stable_order():
    e1 = Entity(entity_uid="j_E1", entity_type="PALLET", model_entity_id="E2", original_index=1)
    e2 = Entity(entity_uid="j_E2", entity_type="PALLET", model_entity_id="E1", original_index=0)
    entities = [e1, e2]
    sort_entities_deterministically(entities)
    assert entities[0].model_entity_id == "E1"
    assert entities[1].model_entity_id == "E2"


def test_sort_entities_deterministically_tie_breaker_original_index():
    e1 = Entity(entity_uid="j_E1", entity_type="PALLET", model_entity_id="E1", original_index=1)
    e2 = Entity(entity_uid="j_E2", entity_type="PALLET", model_entity_id="E1", original_index=0)
    entities = [e1, e2]
    sort_entities_deterministically(entities)
    assert entities[0].original_index == 0
    assert entities[1].original_index == 1


# --- pallet_id resolution ---

def test_resolve_pallet_id_from_barcode():
    e = Entity(entity_uid="j_E1", entity_type="PALLET", model_entity_id="E1", position_barcode="BC-001")
    resolve_pallet_id([e])
    assert e.pallet_id == "BC-001"
    assert e.pallet_id_method == "position_barcode"


def test_resolve_pallet_id_generated_when_no_barcode():
    """Sin position_barcode se asigna PALLET_001, method=generated."""
    e = Entity(entity_uid="j_E1", entity_type="PALLET", model_entity_id="E1")
    resolve_pallet_id([e])
    assert e.pallet_id == "PALLET_001"
    assert e.pallet_id_method == "generated"


def test_resolve_pallet_id_generated_after_sort():
    e2 = Entity(entity_uid="j_E2", entity_type="PALLET", model_entity_id="E2", original_index=1)
    e1 = Entity(entity_uid="j_E1", entity_type="PALLET", model_entity_id="E1", original_index=0)
    entities = [e2, e1]
    sort_entities_deterministically(entities)
    resolve_pallet_id(entities)
    assert entities[0].model_entity_id == "E1"
    assert entities[0].pallet_id == "PALLET_001"
    assert entities[1].pallet_id == "PALLET_002"


def test_resolve_pallet_id_duplicate_barcode_sets_conflict_no_suffix():
    e1 = Entity(entity_uid="j_E1", entity_type="PALLET", model_entity_id="E1", position_barcode="SAME")
    e2 = Entity(entity_uid="j_E2", entity_type="PALLET", model_entity_id="E2", position_barcode="SAME")
    entities = [e1, e2]
    resolve_pallet_id(entities)
    assert e1.pallet_id == "SAME"
    assert e2.pallet_id == "SAME"
    assert e1.conflict_flag is True
    assert e2.conflict_flag is True
    assert e1.conflict_reason == "DUPLICATE_POSITION_BARCODE"
    assert e2.conflict_reason == "DUPLICATE_POSITION_BARCODE"


# --- count_status ---
# Regression: test_assign_count_status_empty_pallet and test_assign_count_status_pallet_*
# ensure EMPTY_PALLET and PALLET behaviour is unchanged after LOOSE_BOXES rule changes.


def test_assign_count_status_empty_pallet():
    e = Entity(entity_uid="j_E1", entity_type="EMPTY_PALLET", model_entity_id="E1")
    assign_count_status(e)
    assert e.count_status == "EMPTY"
    assert e.final_quantity == 0


def test_assign_count_status_loose_boxes_no_evidence():
    """LOOSE_BOXES with no position_barcode, internal_code or quantity → INVALID_STRUCTURE."""
    e = Entity(entity_uid="j_E1", entity_type="LOOSE_BOXES", model_entity_id="E1")
    assign_count_status(e)
    assert e.count_status == "INVALID_STRUCTURE"
    assert e.final_quantity is None


def test_assign_count_status_loose_boxes_counted():
    """LOOSE_BOXES with identity (position or internal_code) and quantity → COUNTED."""
    e_pos = Entity(
        entity_uid="j_E1",
        entity_type="LOOSE_BOXES",
        model_entity_id="E1",
        position_barcode="P1",
        product_label_quantity=8,
    )
    assign_count_status(e_pos)
    assert e_pos.count_status == "COUNTED"
    assert e_pos.final_quantity == 8
    e_sku = Entity(
        entity_uid="j_E2",
        entity_type="LOOSE_BOXES",
        model_entity_id="E2",
        internal_code="SKU-X",
        product_label_quantity=3,
    )
    assign_count_status(e_sku)
    assert e_sku.count_status == "COUNTED"
    assert e_sku.final_quantity == 3


def test_assign_count_status_loose_boxes_needs_review():
    """LOOSE_BOXES with only identity or only quantity → NEEDS_REVIEW."""
    e_pos_only = Entity(
        entity_uid="j_E1",
        entity_type="LOOSE_BOXES",
        model_entity_id="E1",
        position_barcode="P1",
    )
    assign_count_status(e_pos_only)
    assert e_pos_only.count_status == "NEEDS_REVIEW"
    assert e_pos_only.final_quantity is None
    e_qty_only = Entity(
        entity_uid="j_E2",
        entity_type="LOOSE_BOXES",
        model_entity_id="E2",
        product_label_quantity=5,
    )
    assign_count_status(e_qty_only)
    assert e_qty_only.count_status == "NEEDS_REVIEW"
    assert e_qty_only.final_quantity is None


def test_assign_count_status_loose_boxes_qty_zero():
    """LOOSE_BOXES with identity but product_label_quantity=0 → NEEDS_REVIEW (qty not valid for COUNTED)."""
    e = Entity(
        entity_uid="j_E1",
        entity_type="LOOSE_BOXES",
        model_entity_id="E1",
        position_barcode="P1",
        product_label_quantity=0,
    )
    assign_count_status(e)
    assert e.count_status == "NEEDS_REVIEW"
    assert e.final_quantity is None


def test_assign_count_status_loose_boxes_qty_zero_no_identity():
    """LOOSE_BOXES with only product_label_quantity=0 (no identity) → INVALID_STRUCTURE."""
    e = Entity(
        entity_uid="j_E1",
        entity_type="LOOSE_BOXES",
        model_entity_id="E1",
        product_label_quantity=0,
    )
    assign_count_status(e)
    assert e.count_status == "INVALID_STRUCTURE"
    assert e.final_quantity is None


def test_assign_count_status_loose_boxes_conflict_flag():
    """LOOSE_BOXES with conflict_flag set → NEEDS_REVIEW even when identity and qty present."""
    e = Entity(
        entity_uid="j_E1",
        entity_type="LOOSE_BOXES",
        model_entity_id="E1",
        position_barcode="P1",
        product_label_quantity=8,
        conflict_flag=True,
        conflict_reason="DUPLICATE_POSITION_BARCODE",
    )
    assign_count_status(e)
    assert e.count_status == "NEEDS_REVIEW"
    assert e.final_quantity is None


def test_assign_count_status_pallet_counted():
    e = Entity(
        entity_uid="j_E1",
        entity_type="PALLET",
        model_entity_id="E1",
        position_barcode="P1",
        product_label_quantity=10,
    )
    assign_count_status(e)
    assert e.count_status == "COUNTED"
    assert e.final_quantity == 10


def test_assign_count_status_pallet_needs_review_partial():
    e = Entity(entity_uid="j_E1", entity_type="PALLET", model_entity_id="E1", position_barcode="P1")
    assign_count_status(e)
    assert e.count_status == "NEEDS_REVIEW"
    assert e.final_quantity is None


def test_assign_count_status_pallet_not_countable():
    e = Entity(entity_uid="j_E1", entity_type="PALLET", model_entity_id="E1")
    assign_count_status(e)
    assert e.count_status == "NOT_COUNTABLE"
    assert e.final_quantity is None


def test_assign_count_status_conflict_flag_keeps_needs_review():
    e = Entity(
        entity_uid="j_E1",
        entity_type="PALLET",
        model_entity_id="E1",
        position_barcode="P1",
        product_label_quantity=5,
        conflict_flag=True,
        conflict_reason="DUPLICATE_POSITION_BARCODE",
    )
    assign_count_status(e)
    assert e.count_status == "NEEDS_REVIEW"
    assert e.final_quantity is None


def test_assign_count_status_needs_review_final_quantity_none():
    """NEEDS_REVIEW must have final_quantity = None (partial signals)."""
    e = Entity(
        entity_uid="j_E1",
        entity_type="PALLET",
        model_entity_id="E1",
        position_barcode="P1",
        product_label_quantity=10,  # has qty but we could have partial; NEEDS_REVIEW => None
    )
    assign_count_status(e)
    assert e.count_status == "COUNTED"
    assert e.final_quantity == 10
    e2 = Entity(
        entity_uid="j_E2",
        entity_type="PALLET",
        model_entity_id="E2",
        conflict_flag=True,
        conflict_reason="DUPLICATE_POSITION_BARCODE",
    )
    assign_count_status(e2)
    assert e2.count_status == "NEEDS_REVIEW"
    assert e2.final_quantity is None


# --- entity_quality_score ---

def test_entity_quality_score_base_confidence():
    e = Entity(entity_uid="j_E1", entity_type="PALLET", model_entity_id="E1", confidence=0.5)
    compute_entity_quality_score(e)
    assert e.entity_quality_score == 0.5


def test_entity_quality_score_with_position_and_qty_and_boxes():
    e = Entity(
        entity_uid="j_E1",
        entity_type="PALLET",
        model_entity_id="E1",
        confidence=0.4,
        position_barcode="P1",
        product_label_quantity=10,
        has_boxes=True,
    )
    compute_entity_quality_score(e)
    # 0.4 + 0.2 + 0.3 + 0.1 = 1.0
    assert e.entity_quality_score == 1.0


def test_entity_quality_score_clamped():
    e = Entity(
        entity_uid="j_E1",
        entity_type="PALLET",
        model_entity_id="E1",
        confidence=0.9,
        position_barcode="P1",
        product_label_quantity=10,
        has_boxes=True,
    )
    compute_entity_quality_score(e)
    assert e.entity_quality_score == 1.0


# --- Report summary ---

def test_build_summary_from_entities():
    entities = [
        Entity(entity_uid="j_E1", entity_type="PALLET", model_entity_id="E1", count_status="COUNTED"),
        Entity(entity_uid="j_E2", entity_type="EMPTY_PALLET", model_entity_id="E2", count_status="EMPTY"),
        Entity(entity_uid="j_E3", entity_type="PALLET", model_entity_id="E3", count_status="NEEDS_REVIEW"),
    ]
    summary = _build_summary_from_entities(entities)
    assert summary["total_entities"] == 3
    assert summary["pallets"] == 2
    assert summary["empty_pallets"] == 1
    assert summary["counted"] == 1
    assert summary["needs_review"] == 1


def test_build_hybrid_report_v2_1_has_summary_and_entities():
    entities = parse_entities(VALID_V21_PAYLOAD, job_id="j1")
    sort_entities_deterministically(entities)
    resolve_pallet_id(entities)
    for e in entities:
        assign_count_status(e)
    for e in entities:
        compute_entity_quality_score(e)
    report = build_hybrid_report("/path/v.mp4", entities, frames_selected=10)
    assert report["report_version"] == "2.1"
    assert report["mode"] == "hybrid_v2.1"
    assert "summary" in report
    assert report["summary"]["total_entities"] == 2
    assert len(report["entities"]) == 2
    assert report["entities"][0]["entity_quality_score"] >= 0
    assert report["entities"][0]["count_status"] == "COUNTED"
    assert report["entities"][1]["count_status"] == "EMPTY"


def test_build_hybrid_report_v2_1_includes_bboxes_and_integrity_fields():
    """Report v2.1 must include entity_uid, conflict_*, entity_quality_score, bboxes."""
    e = Entity(
        entity_uid="j_E1",
        entity_type="PALLET",
        model_entity_id="E1",
        position_label_bbox=[0.1, 0.2, 0.4, 0.5],
        product_label_bbox=[0.5, 0.0, 0.9, 0.2],
        count_status="COUNTED",
        final_quantity=5,
        conflict_flag=False,
        conflict_reason=None,
        entity_quality_score=0.85,
    )
    report = build_hybrid_report("/path/v.mp4", [e], frames_selected=3)
    ent = report["entities"][0]
    assert ent["entity_uid"] == "j_E1"
    assert ent["conflict_flag"] is False
    assert ent["conflict_reason"] is None
    assert ent["entity_quality_score"] == 0.85
    assert ent["position_label_bbox"] == [0.1, 0.2, 0.4, 0.5]
    assert ent["product_label_bbox"] == [0.5, 0.0, 0.9, 0.2]
    assert isinstance(ent["position_label_bbox"][0], float)
