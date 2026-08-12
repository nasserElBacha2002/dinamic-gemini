"""
In-memory implementation of InventoryRepository — v3.0.

Used for development and for the v3 API when no database is configured.
State is process-local and not persisted across restarts.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from datetime import datetime

from src.application.ports.repositories import InventoryRepository
from src.domain.inventory.entities import Inventory, InventoryStatus


class MemoryInventoryRepository(InventoryRepository):
    def __init__(self) -> None:
        self._store: dict[str, Inventory] = {}
        self._lock = threading.Lock()

    def save(self, inventory: Inventory) -> None:
        with self._lock:
            self._store[inventory.id] = inventory

    def get_by_id(self, inventory_id: str) -> Inventory | None:
        with self._lock:
            return self._store.get(inventory_id)

    def list_all(self) -> Sequence[Inventory]:
        with self._lock:
            return [inv for inv in self._store.values() if not inv.is_deleted]

    def compare_and_set_status(
        self,
        inventory_id: str,
        *,
        expected_current: InventoryStatus,
        new_status: InventoryStatus,
        updated_at: datetime,
        completed_at: datetime | None,
    ) -> bool:
        with self._lock:
            inv = self._store.get(inventory_id)
            if inv is None or inv.status != expected_current:
                return False
            inv.status = new_status
            inv.updated_at = updated_at
            inv.completed_at = completed_at
            return True
