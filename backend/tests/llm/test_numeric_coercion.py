"""Tests for B2.4 LLM numeric coercion (product_label_quantity)."""

from __future__ import annotations

import pytest

from src.llm.normalization.numeric_coercion import (
    coerce_v21_product_label_quantities,
    normalize_optional_int,
)
from src.validation.global_analysis_schema import validate_global_analysis_structure_v21


@pytest.mark.parametrize(
    ("inp", "expected"),
    [
        (None, None),
        (3, 3),
        ("3", 3),
        ("", None),
        ("   ", None),
        ("abc", None),
        (True, None),
        (False, None),
        (3.0, 3),
        (3.5, None),
        ("007", 7),
    ],
)
def test_normalize_optional_int(inp: object, expected: int | None) -> None:
    assert normalize_optional_int(inp) == expected


def test_coerce_v21_product_label_quantities_mutates_entities() -> None:
    data = {
        "total_entities_detected": 2,
        "entities": [
            {"product_label_quantity": "12"},
            {"product_label_quantity": None},
        ],
    }
    coerce_v21_product_label_quantities(data)
    assert data["entities"][0]["product_label_quantity"] == 12
    assert data["entities"][1]["product_label_quantity"] is None


_MINIMAL_ENTITY = {
    "entity_type": "PALLET",
    "model_entity_id": "E1",
    "has_boxes": True,
    "confidence": 0.9,
}


def test_validate_v21_string_quantity_passes_and_coerces_to_int() -> None:
    data = {
        "total_entities_detected": 1,
        "entities": [{**_MINIMAL_ENTITY, "product_label_quantity": "3"}],
    }
    validate_global_analysis_structure_v21(data)
    assert data["entities"][0]["product_label_quantity"] == 3


def test_validate_v21_empty_string_quantity_becomes_none() -> None:
    data = {
        "total_entities_detected": 1,
        "entities": [{**_MINIMAL_ENTITY, "product_label_quantity": ""}],
    }
    validate_global_analysis_structure_v21(data)
    assert data["entities"][0]["product_label_quantity"] is None


def test_validate_v21_non_numeric_string_becomes_none_not_schema_error() -> None:
    data = {
        "total_entities_detected": 1,
        "entities": [{**_MINIMAL_ENTITY, "product_label_quantity": "varios"}],
    }
    validate_global_analysis_structure_v21(data)
    assert data["entities"][0]["product_label_quantity"] is None


def test_validate_v21_preserves_explicit_none() -> None:
    data = {
        "total_entities_detected": 1,
        "entities": [{**_MINIMAL_ENTITY, "product_label_quantity": None}],
    }
    validate_global_analysis_structure_v21(data)
    assert data["entities"][0]["product_label_quantity"] is None


def test_validate_v21_preserves_int() -> None:
    data = {
        "total_entities_detected": 1,
        "entities": [{**_MINIMAL_ENTITY, "product_label_quantity": 3}],
    }
    validate_global_analysis_structure_v21(data)
    assert data["entities"][0]["product_label_quantity"] == 3


def test_validate_v21_unknown_type_quantity_becomes_none() -> None:
    """Non-scalar garbage becomes None via coercion so validation does not fail SCHEMA_INVALID."""
    data = {
        "total_entities_detected": 1,
        "entities": [{**_MINIMAL_ENTITY, "product_label_quantity": object()}],
    }
    validate_global_analysis_structure_v21(data)
    assert data["entities"][0]["product_label_quantity"] is None
