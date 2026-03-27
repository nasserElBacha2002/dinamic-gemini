"""Deterministic natural ordering for human-readable codes (e.g. A2 before A10)."""

from __future__ import annotations

import re
from typing import Any, List, Tuple

_SPLIT_DIGITS = re.compile(r"(\d+)")


def natural_sort_key_parts(text: str) -> Tuple[Any, ...]:
    """Return a tuple usable as sort key so numeric substrings compare numerically."""
    s = (text or "").strip()
    if not s:
        return ("",)
    parts: List[Any] = []
    for chunk in _SPLIT_DIGITS.split(s):
        if chunk == "":
            continue
        if chunk.isdigit():
            parts.append(int(chunk))
        else:
            parts.append(chunk.lower())
    return tuple(parts) if parts else ("",)
