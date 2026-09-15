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
        """Return active inventories (exclude soft-deleted). Order is implementation-defined."""
        with self._lock:
            return [inv for inv in self._store.values() if not inv.is_deleted]

    def list_for_client(self, client_id: str) -> Sequence[Inventory]:
        cid = (client_id or "").strip()
        if not cid:
            return []
        with self._lock:
            return [
                inv
                for inv in self._store.values()
                if not inv.is_deleted and (inv.client_id or "").strip() == cid
            ]

    def soft_delete_many_for_scope(
        self,
        inventory_ids: Sequence[str],
        *,
        allow_all_clients: bool,
        client_id: str | None,
        deleted_at: datetime,
        deleted_by: str | None,
    ) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        with self._lock:
            if not allow_all_clients:
                cid = (client_id or "").strip()
                if not cid:
                    return (), (), tuple(inventory_ids)

            resolved: list[Inventory] = []
            not_found: list[str] = []
            for inventory_id in inventory_ids:
                inventory = self._store.get(inventory_id)
                if inventory is None:
                    not_found.append(inventory_id)
                    continue
                if not allow_all_clients:
                    inv_client = (inventory.client_id or "").strip() or None
                    if inv_client != (client_id or "").strip():
                        not_found.append(inventory_id)
                        continue
                resolved.append(inventory)

            if not_found:
                return (), (), tuple(not_found)

            deleted: list[str] = []
            already: list[str] = []
            for inventory in resolved:
                if inventory.is_deleted:
                    already.append(inventory.id)
                    continue
                changed = inventory.mark_deleted(deleted_at, deleted_by=deleted_by)
                if not changed:
                    already.append(inventory.id)
                    continue
                self._store[inventory.id] = inventory
                deleted.append(inventory.id)
            return tuple(deleted), tuple(already), ()

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
