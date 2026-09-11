"""Integer-only quantity parsing — never truncate 1.5 to 1."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.application.services.image_processing.extraction_profile_configuration import (
    ExtractionProfileConfigurationError,
    parse_extraction_configuration,
)
from src.application.services.label_validation.integer_quantity import (
    IntegerQuantityError,
    coerce_positive_int_quantity,
    parse_integer_quantity,
)
from src.domain.client_supplier.extraction_profile import default_extraction_configuration


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1, 1),
        (12, 12),
        (99_999_999, 99_999_999),
        ("8", 8),
        ("01", 1),
        (16.0, 16),
        (Decimal("7"), 7),
    ],
)
def test_parse_integer_quantity_accepts_integers(value: object, expected: int) -> None:
    assert parse_integer_quantity(value) == expected


@pytest.mark.parametrize(
    "value",
    [1.5, "1.5", "1,5", Decimal("1.5"), 0.1, True, False, "", None, "abc", object()],
)
def test_parse_integer_quantity_rejects_decimals_and_invalid(value: object) -> None:
    with pytest.raises(IntegerQuantityError):
        parse_integer_quantity(value)


def test_parse_integer_quantity_does_not_truncate_decimal() -> None:
    with pytest.raises(IntegerQuantityError) as exc:
        parse_integer_quantity(1.5)
    assert exc.value.code == "QUANTITY_DECIMALS_NOT_SUPPORTED"


def test_parse_integer_quantity_rejects_negative_when_caller_checks_rules() -> None:
    assert parse_integer_quantity(-3) == -3


def test_coerce_positive_int_quantity_bounds() -> None:
    assert coerce_positive_int_quantity(1) == 1
    assert coerce_positive_int_quantity(99_999_999) == 99_999_999
    assert coerce_positive_int_quantity(0) is None
    assert coerce_positive_int_quantity(-1) is None
    assert coerce_positive_int_quantity(1.5) is None
    assert coerce_positive_int_quantity(None) is None


def test_allow_decimals_true_rejected_on_save() -> None:
    raw = default_extraction_configuration().to_public_dict()
    raw["quantity_rules"]["allow_decimals"] = True
    with pytest.raises(ExtractionProfileConfigurationError) as exc:
        parse_extraction_configuration(raw)
    assert exc.value.code == "QUANTITY_DECIMALS_NOT_SUPPORTED"
