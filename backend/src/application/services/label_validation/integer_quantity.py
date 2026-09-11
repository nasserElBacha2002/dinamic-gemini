"""Integer-only quantity parsing. ProductRecord / DB store INT — never truncate decimals."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

_DECIMAL_MARKERS = frozenset(".,")


class IntegerQuantityError(ValueError):
    """Quantity is missing, decimal, or otherwise not a positive-domain integer."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def parse_integer_quantity(value: object) -> int:
    """Parse a quantity as an integer without truncation.

    Accepts ``int`` and integer-valued ``float`` / ``Decimal`` / digit strings.
    Rejects bools, ``1.5``, ``"1.5"``, empty, and non-numeric values.
    Does not invent ``0`` or ``1``.
    """
    if value is None:
        raise IntegerQuantityError("QUANTITY_MISSING", "quantity is required")
    if isinstance(value, bool):
        raise IntegerQuantityError("QUANTITY_NOT_INTEGER", "quantity must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        raise IntegerQuantityError("QUANTITY_DECIMALS_NOT_SUPPORTED", "quantity decimals are not allowed")
    if isinstance(value, Decimal):
        if value != value.to_integral_value():
            raise IntegerQuantityError("QUANTITY_DECIMALS_NOT_SUPPORTED", "quantity decimals are not allowed")
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise IntegerQuantityError("QUANTITY_MISSING", "quantity is required")
        if any(marker in text for marker in _DECIMAL_MARKERS):
            raise IntegerQuantityError("QUANTITY_DECIMALS_NOT_SUPPORTED", "quantity decimals are not allowed")
        if text.startswith("+"):
            text = text[1:]
        try:
            parsed = Decimal(text)
        except InvalidOperation as exc:
            raise IntegerQuantityError("QUANTITY_NOT_INTEGER", "quantity must be an integer") from exc
        if parsed != parsed.to_integral_value():
            raise IntegerQuantityError("QUANTITY_DECIMALS_NOT_SUPPORTED", "quantity decimals are not allowed")
        return int(parsed)
    raise IntegerQuantityError("QUANTITY_NOT_INTEGER", "quantity must be an integer")


def coerce_positive_int_quantity(value: object) -> int | None:
    """Return a positive integer quantity, or None when absent/invalid. Never truncates."""
    if value is None:
        return None
    try:
        parsed = parse_integer_quantity(value)
    except IntegerQuantityError:
        return None
    if parsed <= 0:
        return None
    return parsed
