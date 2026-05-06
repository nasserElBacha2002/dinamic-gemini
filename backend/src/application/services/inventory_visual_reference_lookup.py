"""Small helpers for working with visual reference lists (file route, etc.)."""

from __future__ import annotations

from collections.abc import Sequence

from src.domain.inventory.visual_reference import InventoryVisualReference


def select_visual_reference_by_id(
    refs: Sequence[InventoryVisualReference],
    reference_id: str,
) -> InventoryVisualReference | None:
    """Return the reference with matching ``id``, or ``None``."""
    for r in refs:
        if r.id == reference_id:
            return r
    return None
