"""Coerce LLM numeric fields that may arrive as strings (B2.4 / multi-provider robustness)."""

from __future__ import annotations

import math
from typing import Any


def normalize_optional_int(value: object) -> int | None:
    """Parse optional quantity-like values from JSON/LLM output into int or None.

    - ``None`` → ``None``
    - ``bool`` → ``None`` (avoid treating ``True`` as ``1``)
    - ``int`` → unchanged
    - whole-number ``float`` → ``int``
    - ``str``: strip; empty → ``None``; digits → ``int``; non-numeric → ``None``
    - other types → ``None``
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        if value.is_integer():
            return int(value)
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return None
    return None


def coerce_v21_product_label_quantities(data: dict[str, Any]) -> None:
    """In-place: set ``entities[*].product_label_quantity`` to ``int | None`` per :func:`normalize_optional_int`."""
    entities = data.get("entities")
    if not isinstance(entities, list):
        return
    for ent in entities:
        if isinstance(ent, dict):
            ent["product_label_quantity"] = normalize_optional_int(ent.get("product_label_quantity"))
