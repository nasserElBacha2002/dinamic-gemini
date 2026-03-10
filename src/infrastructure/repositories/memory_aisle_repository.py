"""
In-memory implementation of AisleRepository — v3.0 (Épica 3).

Used when no database is configured or when SQL fallback is used.
list_by_inventory returns aisles in created_at DESC order for consistency with SQL impl.
"""

from __future__ import annotations

from typing import Dict, Optional, Sequence

from src.application.ports.repositories import AisleRepository
from src.domain.aisle.entities import Aisle


class MemoryAisleRepository(AisleRepository):
    def __init__(self) -> None:
        self._store: Dict[str, Aisle] = {}

    def save(self, aisle: Aisle) -> None:
        self._store[aisle.id] = aisle

    def get_by_id(self, aisle_id: str) -> Optional[Aisle]:
        return self._store.get(aisle_id)

    def list_by_inventory(self, inventory_id: str) -> Sequence[Aisle]:
        out = [a for a in self._store.values() if a.inventory_id == inventory_id]
        out.sort(key=lambda a: a.created_at, reverse=True)
        return out

    def get_by_inventory_and_code(self, inventory_id: str, code: str) -> Optional[Aisle]:
        for a in self._store.values():
            if a.inventory_id == inventory_id and a.code == code:
                return a
        return None
