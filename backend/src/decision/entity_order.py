"""
Deterministic entity ordering for v2.1.

Sort entities before assigning generated pallet_id so that same payload
always yields same PALLET_001, PALLET_002, ...
"""

from typing import List

from src.domain.entity import Entity


def sort_entities_deterministically(entities: List[Entity]) -> None:
    """Sort entities in place: primary model_entity_id (string), secondary original_index.

    Must be called before resolve_pallet_id so generated IDs (PALLET_001, ...)
    are assigned in a stable order across runs.
    """
    entities.sort(key=lambda e: (e.model_entity_id, e.original_index))
