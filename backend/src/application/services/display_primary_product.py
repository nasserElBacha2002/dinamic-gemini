"""
Deterministic "display primary" product row for v3 Results / Review / export.

Matches the rule used by:
- ``GET .../aisles/{aisle_id}/positions`` (list)
- ``GET .../positions/{position_id}`` (detail)
- ``GET /api/v3/review-queue/positions``
"""

from __future__ import annotations

from typing import Optional, Sequence

from src.domain.products.entities import ProductRecord


def select_display_primary_product(products: Sequence[ProductRecord]) -> Optional[ProductRecord]:
    """Pick the canonical product row for summaries: earliest ``created_at``, then ``id``."""
    if not products:
        return None
    return sorted(products, key=lambda x: (x.created_at, x.id))[0]
