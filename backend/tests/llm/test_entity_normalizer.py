"""Tests for v2.1 entity JSON normalization (multi-provider)."""

from __future__ import annotations

from src.llm.normalization.entity_normalizer import normalize_llm_response


def test_openai_style_quantity_maps_to_product_label_quantity() -> None:
    inp = {"entities": [{"quantity": 24}]}
    out = normalize_llm_response(inp, "openai")
    assert out["entities"] == [
        {
            "product_label_quantity": 24,
            "position_barcode": None,
            "internal_code": None,
            "position_label_bbox": None,
            "product_label_bbox": None,
        }
    ]
    assert "quantity" not in out["entities"][0]


def test_gemini_style_unchanged_when_canonical_present() -> None:
    """Canonical quantity preserved; alias keys not introduced. Input is not mutated."""
    inp = {
        "total_entities_detected": 1,
        "entities": [
            {
                "model_entity_id": "E1",
                "entity_type": "PALLET",
                "confidence": 0.9,
                "product_label_quantity": 12,
                "position_barcode": "P1",
            }
        ],
    }
    out = normalize_llm_response(inp, "gemini")
    e = out["entities"][0]
    assert e["product_label_quantity"] == 12
    assert e["position_barcode"] == "P1"
    assert "quantity" not in e and "qty" not in e and "detected_quantity" not in e
    assert inp["entities"][0] == {
        "model_entity_id": "E1",
        "entity_type": "PALLET",
        "confidence": 0.9,
        "product_label_quantity": 12,
        "position_barcode": "P1",
    }


def test_mixed_prefers_existing_product_label_quantity() -> None:
    inp = {
        "entities": [
            {
                "product_label_quantity": 10,
                "quantity": 5,
                "qty": 99,
            }
        ]
    }
    out = normalize_llm_response(inp, "openai")
    ent = out["entities"][0]
    assert ent["product_label_quantity"] == 10
    assert "quantity" not in ent
    assert "qty" not in ent


def test_missing_canonical_fields_default_to_none() -> None:
    inp = {"entities": [{}]}
    out = normalize_llm_response(inp, "gemini")
    ent = out["entities"][0]
    assert ent["position_barcode"] is None
    assert ent["internal_code"] is None
    assert ent["position_label_bbox"] is None
    assert ent["product_label_bbox"] is None
    assert ent["product_label_quantity"] is None


def test_alias_priority_quantity_before_qty_before_detected() -> None:
    inp = {"entities": [{"quantity": 1, "qty": 2, "detected_quantity": 3}]}
    out = normalize_llm_response(inp, "openai")
    assert out["entities"][0]["product_label_quantity"] == 1


def test_detected_quantity_used_when_only_alias() -> None:
    inp = {"entities": [{"detected_quantity": 7}]}
    out = normalize_llm_response(inp, "openai")
    assert out["entities"][0]["product_label_quantity"] == 7


def test_quantity_zero_preserved() -> None:
    inp = {"entities": [{"quantity": 0}]}
    out = normalize_llm_response(inp, "openai")
    assert out["entities"][0]["product_label_quantity"] == 0


def test_non_dict_entities_unchanged() -> None:
    inp = {"entities": [None, "x", {"quantity": 1}]}
    out = normalize_llm_response(inp, "openai")
    assert out["entities"][0] is None
    assert out["entities"][1] == "x"
    assert out["entities"][2]["product_label_quantity"] == 1


def test_non_dict_root_returns_empty_dict() -> None:
    assert normalize_llm_response(None, "openai") == {}  # type: ignore[arg-type]
    assert normalize_llm_response([], "openai") == {}  # type: ignore[arg-type]


def test_deep_copy_does_not_mutate_input() -> None:
    inp = {"entities": [{"quantity": 3}]}
    normalize_llm_response(inp, "openai")
    assert inp["entities"][0] == {"quantity": 3}


def test_openai_quantity_and_bbox_map_to_canonical_fields() -> None:
    inp = {
        "entities": [
            {
                "quantity": 24,
                "bbox": [0.1, 0.2, 0.3, 0.4],
            }
        ]
    }
    out = normalize_llm_response(inp, "openai")
    e = out["entities"][0]
    assert e["product_label_quantity"] == 24
    assert e["product_label_bbox"] == [0.1, 0.2, 0.3, 0.4]
    assert e["position_barcode"] is None
    assert e["internal_code"] is None
    assert e["position_label_bbox"] is None
    assert "quantity" not in e
    assert "bbox" not in e


def test_existing_product_label_bbox_not_overridden_by_bbox() -> None:
    canonical = [0.5, 0.5, 0.9, 0.9]
    inp = {
        "entities": [
            {
                "entity_type": "PALLET",
                "product_label_bbox": canonical,
                "bbox": [0.1, 0.2, 0.3, 0.4],
            }
        ]
    }
    out = normalize_llm_response(inp, "openai")
    e = out["entities"][0]
    assert e["product_label_bbox"] == canonical
    assert "bbox" not in e


def test_pallet_bbox_maps_only_to_product_label_not_position() -> None:
    """PALLET: bbox → product_label_bbox; position_label_bbox only if explicitly set."""
    inp = {
        "entities": [
            {
                "entity_type": "PALLET",
                "bbox": [0.0, 0.0, 1.0, 1.0],
            }
        ]
    }
    out = normalize_llm_response(inp, "openai")
    e = out["entities"][0]
    assert e["product_label_bbox"] == [0.0, 0.0, 1.0, 1.0]
    assert e["position_label_bbox"] is None
    assert "bbox" not in e
