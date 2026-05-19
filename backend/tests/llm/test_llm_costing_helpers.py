"""Unit tests for extracted LLM costing helper modules (Phase 1)."""

from __future__ import annotations

from decimal import Decimal

from src.llm.costing_helpers.calculators import compute_per_million, compute_unit
from src.llm.costing_helpers.coercion import as_decimal, get_first, to_int
from src.llm.costing_helpers.formatting import format_money_optional


def test_to_int_non_negative_and_rejects_bool() -> None:
    assert to_int(10) == 10
    assert to_int(-3) == 0
    assert to_int("42") == 42
    assert to_int(True) is None
    assert to_int(None) is None


def test_get_first_returns_first_parseable_key() -> None:
    raw = {"prompt_tokens": 5, "completion_tokens": 3}
    assert get_first(raw, "missing", "prompt_tokens", "completion_tokens") == 5


def test_as_decimal_clamps_negative_to_zero() -> None:
    assert as_decimal("-1.5") == Decimal("0")
    assert as_decimal("2.5") == Decimal("2.5")


def test_format_money_optional_fixed_point_no_scientific() -> None:
    assert format_money_optional(Decimal("0")) == "0.00000000"
    assert format_money_optional(Decimal("0.0125")) == "0.01250000"
    tiny = Decimal("1E-8")
    out = format_money_optional(tiny)
    assert out is not None
    assert "e" not in out.lower()
    assert out == "0.00000001"


def test_compute_per_million_one_million_tokens() -> None:
    assert compute_per_million(1_000_000, Decimal("5")) == Decimal("5.00000000")


def test_compute_unit_quantizes_to_money_precision() -> None:
    assert compute_unit(2, Decimal("0.5")) == Decimal("1.00000000")
