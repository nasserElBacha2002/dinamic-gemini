"""Regression: Claude may emit has_boxes:null — must not fail SCHEMA_INVALID."""

from __future__ import annotations

from src.llm.normalization.entity_normalizer import normalize_llm_response
from src.validation.global_analysis_schema import validate_global_analysis_structure_v21


def test_has_boxes_null_coerced_to_false_before_schema_validate() -> None:
    raw = {
        "total_entities_detected": 1,
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "manifest_entry_id": "IMG_001",
                "confidence": 0.9,
                "has_boxes": None,
                "internal_code": "99090908898",
                "product_label_quantity": 999,
            }
        ],
    }
    normalized = normalize_llm_response(raw, provider="claude")
    assert normalized["entities"][0]["has_boxes"] is False
    validate_global_analysis_structure_v21(normalized)


def test_schema_validate_coerces_null_has_boxes_in_place() -> None:
    data = {
        "total_entities_detected": 1,
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "confidence": 0.5,
                "has_boxes": None,
            }
        ],
    }
    validate_global_analysis_structure_v21(data)
    assert data["entities"][0]["has_boxes"] is False
