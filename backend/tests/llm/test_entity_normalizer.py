"""Tests for v2.1 canonical entity JSON normalization (multi-provider)."""

from __future__ import annotations

import copy

import pytest

from src.llm.normalization.entity_normalizer import (
    EXTRACTION_CONTRACT_VERSION_KEY,
    EXTRACTION_CONTRACT_VERSION_VALUE,
    normalize_llm_response,
    resolve_provider_family,
)
from src.parsing.global_analysis_parser import parse_entities
from src.reporting.display_label import derive_review_display_label
from src.validation.global_analysis_schema import validate_global_analysis_structure_v21
from tests.support.llm_executor_harness import HARNESS_RESPONSE_PROVIDER

# --- Fixtures aligned with real provider shapes (single-entity slices; totals match len(entities)) ---

OPENAI_AUDIT_PAYLOAD = {
    "total_entities_detected": 1,
    "entities": [
        {
            "entity_type": "PALLET",
            "model_entity_id": "entity_1",
            "source_image_id": "473e4c28-fe42-4abd-a61e-2d3961054046",
            "confidence": 0.97,
            "has_boxes": True,
            "quantity": 1,
            "bbox": [0.0, 0.03, 0.94, 0.96],
        },
    ],
}

CLAUDE_AUDIT_PAYLOAD = {
    "total_entities_detected": 1,
    "entities": [
        {
            "entity_type": "PALLET",
            "model_entity_id": "E1",
            "confidence": 0.9,
            "has_boxes": True,
            "source_image_id": "0e832699-c80a-46ac-ad7f-61ac88725f5f",
            "position_label": "INVENTARIO GENERAL 26",
            "position_label_bbox": [0.02, 0.47, 0.35, 0.65],
            "product_label": "1428706",
        },
    ],
}

GEMINI_AUDIT_PAYLOAD = {
    "total_entities_detected": 1,
    "entities": [
        {
            "entity_type": "PALLET",
            "model_entity_id": "E1",
            "position_barcode": None,
            "internal_code": "1428706",
            "position_label_bbox": None,
            "product_label_quantity": None,
            "product_label_bbox": [0.06875, 0.30833333333333335, 0.303125, 0.5944444444444444],
            "has_boxes": True,
            "confidence": 0.95,
            "source_image_id": "473e4c28-fe42-4abd-a61e-2d3961054046",
        },
    ],
}

_CANONICAL_KEYS = (
    "entity_type",
    "model_entity_id",
    "confidence",
    "has_boxes",
    "source_image_id",
    "position_barcode",
    "internal_code",
    "position_label_bbox",
    "product_label_bbox",
    "product_label_quantity",
)


def _assert_canonical_entity_shape(ent: dict) -> None:
    for k in _CANONICAL_KEYS:
        assert k in ent
    assert ent["has_boxes"] is False or ent["has_boxes"] is True


def test_openai_audit_payload_conservative_qty_and_extent_bbox() -> None:
    inp = copy.deepcopy(OPENAI_AUDIT_PAYLOAD)
    out = normalize_llm_response(inp, "openai")
    assert out[EXTRACTION_CONTRACT_VERSION_KEY] == EXTRACTION_CONTRACT_VERSION_VALUE
    assert out["total_entities_detected"] == 1
    e = out["entities"][0]
    _assert_canonical_entity_shape(e)
    assert e["product_label_quantity"] == 1
    assert e["product_label_bbox"] is None
    assert e["extent_bbox"] == [0.0, 0.03, 0.94, 0.96]
    assert "quantity" not in e and "bbox" not in e
    assert e["internal_code"] is None
    assert e["source_image_id"] == "473e4c28-fe42-4abd-a61e-2d3961054046"


def test_claude_audit_payload_maps_product_label_to_internal_code() -> None:
    inp = copy.deepcopy(CLAUDE_AUDIT_PAYLOAD)
    out = normalize_llm_response(inp, "claude")
    e = out["entities"][0]
    _assert_canonical_entity_shape(e)
    assert e["internal_code"] == "1428706"
    assert e["position_label_bbox"] == [0.02, 0.47, 0.35, 0.65]
    assert e["position_barcode"] is None
    assert "product_label" not in e and "position_label" not in e


def test_claude_does_not_map_position_label_to_position_barcode() -> None:
    inp = copy.deepcopy(CLAUDE_AUDIT_PAYLOAD)
    out = normalize_llm_response(inp, "claude")
    assert out["entities"][0]["position_barcode"] is None


def test_gemini_audit_payload_unchanged_semantics() -> None:
    inp = copy.deepcopy(GEMINI_AUDIT_PAYLOAD)
    out = normalize_llm_response(inp, "gemini")
    e = out["entities"][0]
    _assert_canonical_entity_shape(e)
    assert e["internal_code"] == "1428706"
    assert e["product_label_quantity"] is None
    assert e["product_label_bbox"] == GEMINI_AUDIT_PAYLOAD["entities"][0]["product_label_bbox"]
    assert e["source_image_id"] == "473e4c28-fe42-4abd-a61e-2d3961054046"


def test_openai_family_conservative_qty_and_extent_not_product_label_bbox() -> None:
    """OpenAI / GPT keys: positive ``quantity`` + generic ``bbox`` → canonical qty + ``extent_bbox``."""
    inp = {"entities": [{"quantity": 1, "bbox": [0.0, 0.0, 1.0, 1.0]}]}
    out = normalize_llm_response(copy.deepcopy(inp), "openai")
    e = out["entities"][0]
    assert e["product_label_quantity"] == 1
    assert e["product_label_bbox"] is None
    assert e["extent_bbox"] == [0.0, 0.0, 1.0, 1.0]


def test_deepseek_family_mirrors_openai_conservative_qty_and_extent() -> None:
    """DeepSeek uses OpenAI-compatible payloads; same conservative alias rules as openai."""
    inp = {"entities": [{"quantity": 1, "bbox": [0.0, 0.0, 1.0, 1.0]}]}
    out = normalize_llm_response(copy.deepcopy(inp), "deepseek-chat")
    e = out["entities"][0]
    assert e["product_label_quantity"] == 1
    assert e["product_label_bbox"] is None
    assert e["extent_bbox"] == [0.0, 0.0, 1.0, 1.0]


def test_gemini_promotes_aliases_when_canonical_absent() -> None:
    inp = {"entities": [{"quantity": 24, "bbox": [0.1, 0.2, 0.3, 0.4]}]}
    out = normalize_llm_response(inp, "gemini")
    e = out["entities"][0]
    assert e["product_label_quantity"] == 24
    assert e["product_label_bbox"] == [0.1, 0.2, 0.3, 0.4]
    assert "quantity" not in e and "bbox" not in e


def test_harness_provider_promotes_aliases_like_gemini() -> None:
    inp = {"entities": [{"detected_quantity": 7}]}
    out = normalize_llm_response(inp, HARNESS_RESPONSE_PROVIDER)
    assert out["entities"][0]["product_label_quantity"] == 7


def test_non_gemini_preserves_explicit_product_label_quantity_openai() -> None:
    inp = {
        "total_entities_detected": 1,
        "entities": [
            {
                "model_entity_id": "E1",
                "entity_type": "PALLET",
                "confidence": 0.9,
                "has_boxes": True,
                "product_label_quantity": 12,
                "position_barcode": "P1",
                "source_image_id": "x",
            }
        ],
    }
    out = normalize_llm_response(inp, "openai")
    e = out["entities"][0]
    assert e["product_label_quantity"] == 12
    assert e["position_barcode"] == "P1"
    assert "quantity" not in e


def test_mixed_openai_prefers_existing_product_label_quantity_over_quantity_alias() -> None:
    inp = {
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "m",
                "confidence": 0.5,
                "has_boxes": True,
                "source_image_id": None,
                "product_label_quantity": 10,
                "quantity": 5,
                "qty": 99,
            }
        ]
    }
    out = normalize_llm_response(inp, "openai")
    ent = out["entities"][0]
    assert ent["product_label_quantity"] == 10
    assert "quantity" not in ent and "qty" not in ent


def test_missing_fields_filled_for_harness() -> None:
    inp = {"entities": [{}]}
    out = normalize_llm_response(inp, HARNESS_RESPONSE_PROVIDER)
    ent = out["entities"][0]
    _assert_canonical_entity_shape(ent)
    assert ent["position_barcode"] is None
    assert ent["internal_code"] is None
    assert ent["position_label_bbox"] is None
    assert ent["product_label_bbox"] is None
    assert ent["product_label_quantity"] is None
    assert ent["has_boxes"] is False


def test_alias_priority_quantity_before_qty_gemini() -> None:
    inp = {"entities": [{"quantity": 1, "qty": 2, "detected_quantity": 3}]}
    out = normalize_llm_response(inp, "gemini")
    assert out["entities"][0]["product_label_quantity"] == 1


def test_quantity_zero_preserved_gemini_only() -> None:
    inp = {"entities": [{"quantity": 0}]}
    out = normalize_llm_response(inp, "gemini")
    assert out["entities"][0]["product_label_quantity"] == 0


def test_openai_quantity_zero_stripped_not_promoted() -> None:
    inp = {"entities": [{"quantity": 0}]}
    out = normalize_llm_response(inp, "openai")
    assert out["entities"][0]["product_label_quantity"] is None


def test_openai_positive_quantity_promoted_to_canonical_when_missing() -> None:
    inp = {
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "confidence": 0.88,
                "has_boxes": False,
                "source_image_id": "img-1",
                "quantity": 4,
            }
        ]
    }
    out = normalize_llm_response(inp, "openai")
    assert out["entities"][0]["product_label_quantity"] == 4
    assert "quantity" not in out["entities"][0]


def test_openai_extent_bbox_preserved_when_label_bboxes_absent() -> None:
    bbox = [0.05, 0.06, 0.4, 0.5]
    inp = {
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "confidence": 0.5,
                "has_boxes": True,
                "bbox": bbox,
            }
        ]
    }
    out = normalize_llm_response(inp, "openai")
    assert out["entities"][0]["extent_bbox"] == bbox
    assert out["entities"][0]["product_label_bbox"] is None
    assert "bbox" not in out["entities"][0]


def test_non_dict_entities_unchanged() -> None:
    inp = {"entities": [None, "x", {"quantity": 1}]}
    out = normalize_llm_response(inp, "openai")
    assert out["entities"][0] is None
    assert out["entities"][1] == "x"
    # Positive ``quantity`` promotes to canonical qty for openai when product_label_quantity unset.
    assert out["entities"][2]["product_label_quantity"] == 1


def test_non_dict_root_returns_empty_dict() -> None:
    assert normalize_llm_response(None, "openai") == {}  # type: ignore[arg-type]
    assert normalize_llm_response([], "openai") == {}  # type: ignore[arg-type]


def test_deep_copy_does_not_mutate_input() -> None:
    inp = {"entities": [{"quantity": 3}]}
    normalize_llm_response(inp, "openai")
    assert inp["entities"][0] == {"quantity": 3}


def test_existing_product_label_bbox_not_overridden_by_bbox_gemini() -> None:
    canonical = [0.5, 0.5, 0.9, 0.9]
    inp = {
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "m",
                "confidence": 0.9,
                "has_boxes": True,
                "product_label_bbox": canonical,
                "bbox": [0.1, 0.2, 0.3, 0.4],
            }
        ]
    }
    out = normalize_llm_response(inp, "gemini")
    e = out["entities"][0]
    assert e["product_label_bbox"] == canonical
    assert "bbox" not in e


def test_openai_does_not_map_bbox_when_product_bbox_missing() -> None:
    inp = {
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "m",
                "confidence": 0.9,
                "has_boxes": True,
                "bbox": [0.0, 0.0, 1.0, 1.0],
            }
        ]
    }
    out = normalize_llm_response(inp, "openai")
    e = out["entities"][0]
    assert e["product_label_bbox"] is None
    assert e["extent_bbox"] == [0.0, 0.0, 1.0, 1.0]
    assert "bbox" not in e


def test_root_contract_version_and_total_alignment() -> None:
    inp = {"total_entities_detected": 99, "entities": [{"entity_type": "PALLET", "model_entity_id": "a"}]}
    out = normalize_llm_response(inp, "openai")
    assert out["total_entities_detected"] == 1
    assert out[EXTRACTION_CONTRACT_VERSION_KEY] == EXTRACTION_CONTRACT_VERSION_VALUE


def test_claude_internal_code_not_overwritten_when_set() -> None:
    inp = {
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "confidence": 0.9,
                "has_boxes": True,
                "internal_code": "KEEP",
                "product_label": "1428706",
            }
        ]
    }
    out = normalize_llm_response(inp, "claude")
    assert out["entities"][0]["internal_code"] == "KEEP"


@pytest.mark.parametrize("provider", ["unknown_vendor", ""])
def test_unknown_provider_does_not_apply_conservative_qty_or_extent_bbox(provider: str) -> None:
    inp = {"entities": [{"quantity": 5, "bbox": [0, 0, 1, 1]}]}
    out = normalize_llm_response(inp, provider)
    e = out["entities"][0]
    assert e["product_label_quantity"] is None
    assert e["product_label_bbox"] is None
    assert e.get("extent_bbox") is None


def test_claude_strips_quantity_and_bbox_without_conservative_promotion() -> None:
    inp = {
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "confidence": 0.9,
                "has_boxes": False,
                "quantity": 5,
                "bbox": [0.0, 0.0, 1.0, 1.0],
            }
        ]
    }
    out = normalize_llm_response(inp, "claude")
    e = out["entities"][0]
    assert e["product_label_quantity"] is None
    assert e["product_label_bbox"] is None
    assert e.get("extent_bbox") is None
    assert "quantity" not in e and "bbox" not in e


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("openai", "openai"),
        ("OpenAI", "openai"),
        ("openai_sdk", "openai"),
        ("gpt-4.1", "openai"),
        ("anthropic", "claude"),
        ("claude-3-opus", "claude"),
        ("Claude", "claude"),
        ("gemini", "gemini"),
        ("gemini-2.0-flash-exp", "gemini"),
        ("google_genai", "gemini"),
        ("deepseek-chat", "deepseek"),
        ("test_llm", "test_llm"),
        ("", "unknown"),
        ("some_other_vendor", "unknown"),
    ],
)
def test_resolve_provider_family(raw: str, expected: str) -> None:
    assert resolve_provider_family(raw) == expected


def test_openai_canonical_payload_preserved_no_overwrite() -> None:
    """When OpenAI already returns v2.1 canonical fields, pass through unchanged semantics."""
    inp = {
        "total_entities_detected": 1,
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "confidence": 0.9,
                "has_boxes": True,
                "source_image_id": "x",
                "internal_code": "SKU1",
                "product_label_quantity": 5,
                "product_label_bbox": [0.1, 0.2, 0.3, 0.4],
                "position_barcode": None,
                "position_label_bbox": None,
            }
        ],
    }
    expected_ic = inp["entities"][0]["internal_code"]
    expected_qty = inp["entities"][0]["product_label_quantity"]
    expected_bbox = list(inp["entities"][0]["product_label_bbox"])
    out = normalize_llm_response(copy.deepcopy(inp), "openai_sdk")
    e = out["entities"][0]
    assert e["internal_code"] == expected_ic
    assert e["product_label_quantity"] == expected_qty
    assert e["product_label_bbox"] == expected_bbox
    assert "quantity" not in e and "bbox" not in e


def test_openai_maps_product_label_to_internal_code_conservatively() -> None:
    inp = {
        "total_entities_detected": 1,
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "confidence": 0.9,
                "has_boxes": True,
                "source_image_id": "img-1",
                "product_label": "SKU-123_45",
            }
        ],
    }
    out = normalize_llm_response(copy.deepcopy(inp), "openai")
    assert out["entities"][0]["internal_code"] == "SKU-123_45"


def test_openai_does_not_override_existing_internal_code_from_product_label() -> None:
    inp = {
        "total_entities_detected": 1,
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "confidence": 0.9,
                "has_boxes": True,
                "source_image_id": "img-1",
                "internal_code": "KEEP-ME",
                "product_label": "SKU-NEW",
            }
        ],
    }
    out = normalize_llm_response(copy.deepcopy(inp), "openai")
    assert out["entities"][0]["internal_code"] == "KEEP-ME"


def test_openai_does_not_map_invalid_product_label_to_internal_code() -> None:
    inp = {
        "total_entities_detected": 1,
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "confidence": 0.9,
                "has_boxes": True,
                "source_image_id": "img-1",
                "product_label": "NOT VALID WITH SPACES",
            }
        ],
    }
    out = normalize_llm_response(copy.deepcopy(inp), "openai")
    assert out["entities"][0]["internal_code"] is None


def test_openai_normalize_parse_preserves_internal_code_and_canonical_fields() -> None:
    inp = {
        "total_entities_detected": 1,
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "confidence": 0.9,
                "has_boxes": True,
                "source_image_id": "img-1",
                "product_label": "SKU123",
                "quantity": 8,
                "bbox": [0.1, 0.1, 0.8, 0.9],
                "product_label_bbox": [0.2, 0.2, 0.4, 0.4],
                "position_barcode": "POS-777",
            }
        ],
    }
    normalized = normalize_llm_response(copy.deepcopy(inp), "openai")
    validate_global_analysis_structure_v21(normalized)
    entities = parse_entities(normalized, job_id="job-openai-int")
    assert len(entities) == 1
    ent = entities[0]
    assert ent.internal_code == "SKU123"
    assert ent.position_barcode == "POS-777"
    assert ent.product_label_quantity == 8
    assert ent.product_label_bbox == [0.2, 0.2, 0.4, 0.4]
    assert ent.source_image_id == "img-1"


def test_openai_quantity_only_response_does_not_create_fake_internal_code() -> None:
    inp = {
        "total_entities_detected": 1,
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "confidence": 0.9,
                "has_boxes": True,
                "source_image_id": "img-1",
                "quantity": 6,
            }
        ],
    }
    normalized = normalize_llm_response(copy.deepcopy(inp), "openai")
    validate_global_analysis_structure_v21(normalized)
    entities = parse_entities(normalized, job_id="job-openai-qty")
    assert entities[0].internal_code is None
    assert entities[0].product_label_quantity == 6


def test_claude_audit_payload_via_anthropic_provider_string() -> None:
    out = normalize_llm_response(copy.deepcopy(CLAUDE_AUDIT_PAYLOAD), "Anthropic")
    assert out["entities"][0]["internal_code"] == "1428706"


def test_claude_product_label_not_mapped_when_invalid_oocr() -> None:
    """Noisy / overlong OCR must not become internal_code."""
    inp = {
        "total_entities_detected": 1,
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "confidence": 0.9,
                "has_boxes": True,
                "source_image_id": "s",
                "product_label": "NOT A VALID CODE WITH SPACES",
            }
        ],
    }
    out = normalize_llm_response(inp, "claude")
    assert out["entities"][0]["internal_code"] is None

    long_token = "A" * 49
    inp2 = {
        "total_entities_detected": 1,
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "confidence": 0.9,
                "has_boxes": True,
                "source_image_id": "s",
                "product_label": long_token,
            }
        ],
    }
    out2 = normalize_llm_response(inp2, "claude")
    assert out2["entities"][0]["internal_code"] is None


def test_claude_normalize_parse_entities_and_review_display_label() -> None:
    """Integration: Claude OCR survives normalization and reaches parser + display derivation."""
    normalized = normalize_llm_response(copy.deepcopy(CLAUDE_AUDIT_PAYLOAD), "claude-3-sonnet")
    validate_global_analysis_structure_v21(normalized)
    entities = parse_entities(normalized, job_id="job-claude-int")
    assert len(entities) == 1
    ent = entities[0]
    assert ent.internal_code == "1428706"
    label = derive_review_display_label(ent.internal_code, ent.position_barcode)
    assert label == "1428706"
    assert label is not None
    assert str(label).lower() != "unknown"


def test_gpt_provider_family_normalizes_like_openai_family() -> None:
    inp = {"entities": [{"quantity": 1, "bbox": [0.0, 0.0, 1.0, 1.0]}]}
    out = normalize_llm_response(inp, "GPT-4.1")
    e = out["entities"][0]
    assert e["product_label_quantity"] == 1
    assert e["product_label_bbox"] is None
    assert e["extent_bbox"] == [0.0, 0.0, 1.0, 1.0]
