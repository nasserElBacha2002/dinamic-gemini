"""Pure coercion helpers for LLM usage and pricing fields."""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def to_int(value: Any) -> int | None:
    """Parse non-negative int from common JSON/provider shapes (B8.5 — single exit)."""
    out: int | None = None
    if value is None or isinstance(value, bool):
        out = None
    elif isinstance(value, int):
        out = max(0, value)
    elif isinstance(value, float):
        if value != value:  # NaN
            out = None
        else:
            out = max(0, int(value))
    elif isinstance(value, str):
        raw = value.strip()
        if raw:
            try:
                out = max(0, int(raw))
            except ValueError:
                out = None
        else:
            out = None
    else:
        out = None
    return out


def get_first(raw: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        if key in raw:
            parsed = to_int(raw.get(key))
            if parsed is not None:
                return parsed
    return None


def as_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        dec = Decimal(str(value))
    except Exception:
        return None
    return Decimal("0") if dec < 0 else dec


def usage_int(usage: dict[str, Any], key: str) -> int | None:
    value = usage.get(key)
    return to_int(value) if value is not None else None
