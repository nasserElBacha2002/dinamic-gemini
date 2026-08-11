"""Explicit CAS helpers for InventoryRepository test doubles.

Production SQL/Memory repositories implement true atomic CAS. Test stubs must
still satisfy the abstract contract without inheriting a non-atomic ABC default.
"""

from __future__ import annotations

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
