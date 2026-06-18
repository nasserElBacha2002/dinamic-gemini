"""Runtime + parser compatibility for label-first payloads under the v2.1 entities[] contract."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.llm.normalization.entity_normalizer import normalize_llm_response
from src.llm.prompt_composer.hybrid_assembly import (
    compose_hybrid_base,
    resolve_hybrid_profile_name,
)
from src.parsing.global_analysis_parser import parse_entities
from src.validation.global_analysis_schema import validate_global_analysis_structure_v21

# Realistic label-first style response (same root contract as global_v21 / global_v22 prompts).
_LABEL_FIRST_V22_STYLE_PAYLOAD: dict = {
    "total_entities_detected": 2,
    "entities": [
        {
            "entity_type": "PALLET",
            "model_entity_id": "entity_1",
            "internal_code": "10334301",
            "product_label_quantity": 16,
            "source_image_id": "img-1",
            "confidence": 0.94,
            "has_boxes": True,
        },
        {
            "entity_type": "EMPTY_PALLET",
            "model_entity_id": "entity_2",
            "internal_code": None,
            "product_label_quantity": 0,
            "source_image_id": "img-2",
            "confidence": 0.91,
            "has_boxes": False,
        },
    ],
}


def test_label_first_payload_passes_v21_validator() -> None:
    validate_global_analysis_structure_v21(_LABEL_FIRST_V22_STYLE_PAYLOAD)


def test_resolve_hybrid_profile_always_global_v22() -> None:
    settings = MagicMock()
    settings.hybrid_prompt = "global_v21"
    assert resolve_hybrid_profile_name(job_prompt_key="global_v22", settings=settings) == "global_v22"
    assert resolve_hybrid_profile_name(job_prompt_key=None, settings=settings) == "global_v22"
    assert resolve_hybrid_profile_name(job_prompt_key="global_v21", settings=settings) == "global_v22"


def test_global_v22_openai_compose_still_provider_overlay_not_downgrade() -> None:
    """OpenAI branch must use v22 OpenAI fragment, not silently fall back to v21."""
    g = compose_hybrid_base("global_v22", None)
    o = compose_hybrid_base("global_v22", "openai")
    assert g != o
    assert "Return valid JSON only" in o
    assert "label-first" in o.lower()


def test_label_first_payload_normalize_parse_roundtrip_gemini() -> None:
    validate_global_analysis_structure_v21(_LABEL_FIRST_V22_STYLE_PAYLOAD)
    normalized = normalize_llm_response(_LABEL_FIRST_V22_STYLE_PAYLOAD, "gemini")
    assert normalized["total_entities_detected"] == 2
    assert len(normalized["entities"]) == 2
    validate_global_analysis_structure_v21(normalized)

    entities = parse_entities(normalized, job_id="job-abc")
    assert len(entities) == 2
    assert entities[0].model_entity_id == "entity_1"
    assert entities[0].internal_code == "10334301"
    assert entities[0].product_label_quantity == 16
    assert entities[0].raw_source_image_id == "img-1"
    assert entities[1].entity_type == "EMPTY_PALLET"
    assert entities[1].product_label_quantity == 0
    assert entities[1].raw_source_image_id == "img-2"


def test_optional_entity_metadata_accepted_by_validator_preserved_in_normalized_dict_dropped_by_parser() -> None:
    """Document behavior: extra keys are not rejected by validate_v21; normalizer does not strip them;
    parse_entities maps only canonical Entity fields (metadata not on domain object)."""
    data = {
        "total_entities_detected": 1,
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "has_boxes": True,
                "confidence": 0.9,
                "internal_code": "X1",
                "product_label_quantity": 4,
                "source_image_id": "img-a",
                "label_detected": True,
                "label_readable": True,
                "quantity_source": "LABEL",
                "raw_label_text": "X1 / 4",
                "requires_review": False,
            },
        ],
    }
    validate_global_analysis_structure_v21(data)
    normalized = normalize_llm_response(data, "gemini")
    ent = normalized["entities"][0]
    assert ent.get("raw_label_text") == "X1 / 4"
    assert ent.get("quantity_source") == "LABEL"

    parsed = parse_entities(normalized, job_id="j1")
    assert parsed[0].internal_code == "X1"
    assert getattr(parsed[0], "raw_label_text", None) is None
