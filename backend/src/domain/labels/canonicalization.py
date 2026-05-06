"""
SKU canonicalization — v3.2.3.

Basic normalization only: trim, casing, repeated spaces, simple separators.
No fuzzy/semantic matching.
"""

from __future__ import annotations

import re


def canonicalize_sku(raw: str | None) -> str | None:
    """
    Normalize SKU for merge comparison.

    - Trim, uppercase, collapse repeated spaces.
    - Normalize common separators (multiple dashes/underscores → single).
    - Empty or whitespace-only → None.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    s = s.upper()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[-_]+", "-", s)
    s = s.strip("- _")
    return s or None
