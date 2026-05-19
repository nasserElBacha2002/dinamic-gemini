"""Characterization tests for ``_total_cost_unavailable_reason`` priority ladder."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.llm.costing import _total_cost_unavailable_reason


@pytest.mark.parametrize(
    (
        "total_cost",
        "partial_total_cost",
        "notes",
        "ambiguous",
        "has_usage_metadata",
        "expected",
    ),
    [
        (Decimal("1"), None, [], False, True, None),
        (
            None,
            None,
            ["provider_usage_missing", "pricing_entry_missing:x"],
            False,
            False,
            "provider_usage_missing",
        ),
        (
            None,
            None,
            ["canonical_model_without_catalog_entry"],
            False,
            True,
            "canonical_model_without_catalog_entry",
        ),
        (
            None,
            None,
            [
                "canonical_model_without_catalog_entry:provider=openai,model=a,canonical_model=b"
            ],
            False,
            True,
            "canonical_model_without_catalog_entry",
        ),
        (
            None,
            None,
            ["pricing_entry_missing"],
            False,
            True,
            "pricing_entry_missing",
        ),
        (
            None,
            None,
            ["pricing_entry_missing:provider=gemini,model=x,canonical_model=x"],
            False,
            True,
            "pricing_entry_missing",
        ),
        (
            None,
            Decimal("0.00050000"),
            ["billable_dimension_not_priced:output_tokens"],
            False,
            True,
            "billable_dimension_not_priced",
        ),
        (
            None,
            None,
            ["billable_dimension_not_priced:output_tokens"],
            False,
            True,
            "billable_dimension_not_priced",
        ),
        (
            None,
            None,
            ["pricing_present_but_no_billable_dimensions"],
            False,
            True,
            "pricing_present_but_no_billable_dimensions",
        ),
        (
            None,
            None,
            ["usage_dimension_ambiguous:cached_input"],
            True,
            True,
            "usage_dimension_ambiguous",
        ),
        (
            None,
            None,
            [],
            False,
            True,
            "cost_not_computed",
        ),
        (
            None,
            None,
            [],
            False,
            False,
            None,
        ),
    ],
)
def test_total_cost_unavailable_reason_ladder(
    total_cost: Decimal | None,
    partial_total_cost: Decimal | None,
    notes: list[str],
    ambiguous: bool,
    has_usage_metadata: bool,
    expected: str | None,
) -> None:
    assert (
        _total_cost_unavailable_reason(
            total_cost=total_cost,
            partial_total_cost=partial_total_cost,
            notes=list(notes),
            ambiguous=ambiguous,
            has_usage_metadata=has_usage_metadata,
        )
        == expected
    )


def test_total_cost_unavailable_reason_priority_canonical_over_pricing_missing() -> None:
    notes = [
        "pricing_entry_missing:provider=openai,model=x,canonical_model=x",
        "canonical_model_without_catalog_entry",
    ]
    assert (
        _total_cost_unavailable_reason(
            total_cost=None,
            partial_total_cost=None,
            notes=notes,
            ambiguous=False,
            has_usage_metadata=True,
        )
        == "canonical_model_without_catalog_entry"
    )


def test_total_cost_unavailable_reason_priority_pricing_missing_over_partial() -> None:
    assert (
        _total_cost_unavailable_reason(
            total_cost=None,
            partial_total_cost=Decimal("0.001"),
            notes=["pricing_entry_missing:provider=openai,model=x,canonical_model=x"],
            ambiguous=False,
            has_usage_metadata=True,
        )
        == "pricing_entry_missing"
    )


def test_total_cost_unavailable_reason_priority_partial_over_billable_note_only() -> None:
    assert (
        _total_cost_unavailable_reason(
            total_cost=None,
            partial_total_cost=Decimal("0.00050000"),
            notes=["billable_dimension_not_priced:output_tokens"],
            ambiguous=False,
            has_usage_metadata=True,
        )
        == "billable_dimension_not_priced"
    )
