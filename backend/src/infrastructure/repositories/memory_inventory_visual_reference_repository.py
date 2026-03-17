"""
In-memory implementation of InventoryVisualReferenceRepository — v3.2.4.

Used when SQL is not configured. State is process-local and not persisted.
"""

from __future__ import annotations

from typing import Dict, Sequence

from src.application.ports.repositories import InventoryVisualReferenceRepository
from src.domain.inventory.visual_reference import InventoryVisualReference


class MemoryInventoryVisualReferenceRepository(InventoryVisualReferenceRepository):
    def __init__(self) -> None:
        self._store: Dict[str, InventoryVisualReference] = {}

    def create(self, reference: InventoryVisualReference) -> None:
        if reference.id in self._store:
            raise ValueError(f"InventoryVisualReference with id={reference.id!r} already exists")
        self._store[reference.id] = reference

    def list_by_inventory(self, inventory_id: str) -> Sequence[InventoryVisualReference]:
        refs = [r for r in self._store.values() if r.inventory_id == inventory_id]
        refs.sort(key=lambda r: (r.created_at, r.id))
        return refs
