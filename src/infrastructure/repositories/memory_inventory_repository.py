"""
In-memory implementation of InventoryRepository — v3.0.

Used for development and for the v3 API when no database is configured.
State is process-local and not persisted across restarts.
"""

from __future__ import annotations

from typing import Dict, Optional, Sequence

from src.application.ports.repositories import InventoryRepository
from src.domain.inventory.entities import Inventory


class MemoryInventoryRepository(InventoryRepository):
    def __init__(self) -> None:
        self._store: Dict[str, Inventory] = {}

    def save(self, inventory: Inventory) -> None:
        self._store[inventory.id] = inventory

    def get_by_id(self, inventory_id: str) -> Optional[Inventory]:
        return self._store.get(inventory_id)

    def list_all(self) -> Sequence[Inventory]:
        return list(self._store.values())
