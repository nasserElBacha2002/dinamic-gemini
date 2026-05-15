"""Phase 3 — controlled validation fixtures (no live LLM): v2.1 JSON + prompt comparison.

Documents parser/validator/normalizer behavior for label-first style payloads.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.application.services.supplier_prompt_resolver import SupplierPromptResolution
from src.jobs.image_identity import JobImage
from src.llm.normalization.entity_normalizer import normalize_llm_response
from src.llm.prompt_composer.enrichments import enrich_prompt_with_image_ids
from src.llm.prompt_composer.hybrid_assembly import (
    DEFAULT_HYBRID_PROMPT_PROFILE,
    compose_hybrid_base,
    resolve_hybrid_profile_name,
)
from src.llm.prompts import get_hybrid_prompt
from src.parsing.global_analysis_parser import parse_entities
from src.pipeline.services.effective_prompt_composer import (
    EffectivePromptComposer,
    EffectivePromptComposerInput,
)
from src.validation.global_analysis_schema import validate_global_analysis_structure_v21

# --- A: single labeled pallet ---
FIXTURE_A_LABELED_PALLET: dict = {
    "total_entities_detected": 1,
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
    ],
}

# --- B: two distinct labels / positions ---
FIXTURE_B_TWO_LABELS: dict = {
    "total_entities_detected": 2,
    "entities": [
        {
            "entity_type": "PALLET",
            "model_entity_id": "entity_a",
            "internal_code": "SKU-A",
            "product_label_quantity": 8,
            "source_image_id": "img-1",
            "confidence": 0.93,
            "has_boxes": True,
        },
        {
            "entity_type": "PALLET",
            "model_entity_id": "entity_b",
            "internal_code": "SKU-B",
            "product_label_quantity": 12,
            "source_image_id": "img-2",
            "confidence": 0.9,
            "has_boxes": True,
        },
    ],
}

# --- C: partial / weak evidence ---
FIXTURE_C_PARTIAL_LABEL: dict = {
    "total_entities_detected": 1,
    "entities": [
        {
            "entity_type": "PALLET",
            "model_entity_id": "entity_p1",
            "internal_code": None,
            "product_label_quantity": None,
            "source_image_id": "img-blur",
            "confidence": 0.42,
            "has_boxes": True,
        },
    ],
}

# --- D: unlabeled physical pallet ---
FIXTURE_D_UNLABELED_PALLET: dict = {
    "total_entities_detected": 1,
    "entities": [
        {
            "entity_type": "PALLET",
            "model_entity_id": "entity_u1",
            "internal_code": None,
            "product_label_quantity": None,
            "source_image_id": "img-wide",
            "confidence": 0.78,
            "has_boxes": True,
        },
    ],
}

# --- E: empty pallet (null quantity; contract prefers null when no printed qty) ---
FIXTURE_E_EMPTY_PALLET_NULL_QTY: dict = {
    "total_entities_detected": 1,
    "entities": [
        {
            "entity_type": "EMPTY_PALLET",
            "model_entity_id": "entity_e1",
            "internal_code": None,
            "product_label_quantity": None,
            "source_image_id": "img-empty",
            "confidence": 0.88,
            "has_boxes": False,
        },
    ],
}

# --- E-alt: empty pallet with quantity 0 (schema allows int) ---
FIXTURE_E_EMPTY_PALLET_ZERO_QTY: dict = {
    "total_entities_detected": 1,
    "entities": [
        {
            "entity_type": "EMPTY_PALLET",
            "model_entity_id": "entity_e0",
            "internal_code": None,
            "product_label_quantity": 0,
            "source_image_id": "img-empty-2",
            "confidence": 0.91,
            "has_boxes": False,
        },
    ],
}

# --- F: supplier-style fallback to quantity 1 (no quantity_source metadata in wire contract) ---
FIXTURE_F_SUPPLIER_FALLBACK_QTY_ONE: dict = {
    "total_entities_detected": 1,
    "entities": [
        {
            "entity_type": "PALLET",
            "model_entity_id": "entity_fb",
            "internal_code": None,
            "product_label_quantity": 1,
            "source_image_id": "img-fb",
            "confidence": 0.55,
            "has_boxes": True,
        },
    ],
}


@pytest.mark.parametrize(
    "fixture_name,fixture",
    [
        ("A", FIXTURE_A_LABELED_PALLET),
        ("B", FIXTURE_B_TWO_LABELS),
        ("C", FIXTURE_C_PARTIAL_LABEL),
        ("D", FIXTURE_D_UNLABELED_PALLET),
        ("E_null", FIXTURE_E_EMPTY_PALLET_NULL_QTY),
        ("E_zero", FIXTURE_E_EMPTY_PALLET_ZERO_QTY),
        ("F_fallback_qty", FIXTURE_F_SUPPLIER_FALLBACK_QTY_ONE),
    ],
)
def test_phase3_fixtures_validate_parse_normalize_gemini(
    fixture_name: str, fixture: dict
) -> None:
    validate_global_analysis_structure_v21(fixture)
    normalized = normalize_llm_response(fixture, "gemini")
    assert normalized["total_entities_detected"] == len(normalized["entities"])
    validate_global_analysis_structure_v21(normalized)
    entities = parse_entities(normalized, job_id=f"job-{fixture_name}")
    assert len(entities) == len(fixture["entities"])
    for ent in entities:
        assert ent.source_image_id is not None
        assert 0.0 <= ent.confidence <= 1.0


def test_phase3_fixture_b_distinct_internal_codes_and_image_ids() -> None:
    data = normalize_llm_response(FIXTURE_B_TWO_LABELS, "gemini")
    ents = parse_entities(data, job_id="job-b")
    assert ents[0].internal_code == "SKU-A"
    assert ents[1].internal_code == "SKU-B"
    assert ents[0].source_image_id == "img-1"
    assert ents[1].source_image_id == "img-2"


def test_phase3_supplier_fallback_payload_no_quantity_source_field() -> None:
    """Known limitation: quantity=1 cannot be distinguished from a true label read without metadata."""
    validate_global_analysis_structure_v21(FIXTURE_F_SUPPLIER_FALLBACK_QTY_ONE)
    ent = parse_entities(
        normalize_llm_response(FIXTURE_F_SUPPLIER_FALLBACK_QTY_ONE, "gemini"),
        job_id="j",
    )[0]
    assert ent.product_label_quantity == 1
    assert "quantity_source" not in FIXTURE_F_SUPPLIER_FALLBACK_QTY_ONE["entities"][0]


def test_phase3_prompt_v21_unchanged_v22_label_first_distinct() -> None:
    v21 = compose_hybrid_base("global_v21", None, restrict_to_default_aisle_profile=False)
    v22 = compose_hybrid_base("global_v22", None)
    assert v21 != v22
    assert "logistic" in v21.lower() or "logistic entities" in v21.lower()
    assert "label-first" in v22.lower()
    assert "total_entities_detected" in v22.lower()
    assert "entities" in v22.lower()
    assert "total_positions_detected" not in v22


def test_phase3_prompt_v22_openai_overlay_not_positions_root() -> None:
    o = compose_hybrid_base("global_v22", "openai")
    assert "total_entities_detected" in o
    assert "total_positions_detected" not in o


def test_phase3_get_hybrid_prompt_default_profile_is_v22() -> None:
    assert DEFAULT_HYBRID_PROMPT_PROFILE == "global_v22"
    text = get_hybrid_prompt()
    assert "label-first" in text.lower()


def test_phase3_resolve_profile_empty_settings_hybrid_uses_default_constant() -> None:
    settings = SimpleNamespace(hybrid_prompt="")
    assert resolve_hybrid_profile_name(job_prompt_key=None, settings=settings) == "global_v22"


def test_phase3_resolve_profile_explicit_global_v21_does_not_override_policy_v22() -> None:
    settings = SimpleNamespace(hybrid_prompt="global_v22")
    assert (
        resolve_hybrid_profile_name(job_prompt_key="global_v21", settings=settings) == "global_v22"
    )


def test_phase3_traceability_enrichment_on_v22_base() -> None:
    base = compose_hybrid_base("global_v22", None)
    images = [
        JobImage(
            image_id="p3-img",
            original_filename="x.jpg",
            upload_order=1,
            storage_path="p/x.jpg",
        )
    ]
    out = enrich_prompt_with_image_ids(base, images)
    assert "p3-img" in out
    assert "source_image_id" in out


def test_phase3_supplier_appended_after_enriched_v22_base() -> None:
    base = enrich_prompt_with_image_ids(
        compose_hybrid_base("global_v22", None),
        [
            JobImage(
                image_id="p3-s",
                original_filename="s.jpg",
                upload_order=1,
                storage_path="p/s.jpg",
            )
        ],
    )
    res = SupplierPromptResolution(
        inventory_id="i",
        aisle_id="a",
        client_id="c",
        client_supplier_id="s",
        provider_name="gemini",
        model_name=None,
        supplier_prompt_config_id="cfg",
        supplier_prompt_config_version=1,
        editable_instructions="Read small labels first.",
        fallback_used=False,
        fallback_reason=None,
        resolution_status="resolved",
        warnings=(),
        error_code=None,
    )
    out = EffectivePromptComposer().compose(
        EffectivePromptComposerInput(
            protected_prompt_text=base,
            provider_name="gemini",
            model_name=None,
            supplier_resolution=res,
        )
    ).effective_prompt_text
    assert out.index("TRACEABILITY (v3.1)") < out.index("--- SUPPLIER-SPECIFIC EDITABLE INSTRUCTIONS ---")
    assert "must not override the protected JSON output contract" in out
