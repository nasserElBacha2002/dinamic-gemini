"""Explicit CAS / soft-delete helpers for InventoryRepository test doubles.

Production SQL/Memory repositories implement true atomic operations. Test stubs must
still satisfy the abstract contract without inheriting a non-atomic ABC default.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from src.domain.inventory.entities import Inventory, InventoryStatus


class _InventoryStore(Protocol):
    def get_by_id(self, inventory_id: str) -> Inventory | None: ...

    def save(self, inventory: Inventory) -> None: ...


class ExplicitInventoryCompareAndSet:
    """Mixin: implement ``compare_and_set_status`` via get/check/save.

    Suitable for single-threaded unit stubs. Not evidence of SQL concurrency.
    """

    def compare_and_set_status(
        self: _InventoryStore,
        inventory_id: str,
        *,
        expected_current: InventoryStatus,
        new_status: InventoryStatus,
        updated_at: datetime,
        completed_at: datetime | None,
    ) -> bool:
        inv = self.get_by_id(inventory_id)
        if inv is None or inv.status != expected_current:
            return False
        inv.status = new_status
        inv.updated_at = updated_at
        inv.completed_at = completed_at
        self.save(inv)
        return True

    def soft_delete_many_for_scope(
        self: _InventoryStore,
        inventory_ids: Sequence[str],
        *,
        allow_all_clients: bool,
        client_id: str | None,
        deleted_at: datetime,
        deleted_by: str | None,
    ) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        """Authorize-all then write for single-threaded stubs (not SQL atomicity evidence)."""
        if not allow_all_clients:
            cid = (client_id or "").strip()
            if not cid:
                return (), (), tuple(inventory_ids)

        resolved: list[Inventory] = []
        not_found: list[str] = []
        for inventory_id in inventory_ids:
            inventory = self.get_by_id(inventory_id)
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
            self.save(inventory)
            deleted.append(inventory.id)
        return tuple(deleted), tuple(already), ()
