"""Tests for ListInventoriesUseCase."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.ports.repositories import InventoryRepository
from src.application.use_cases.inventories.list_inventories import ListInventoriesUseCase
from src.domain.inventory.entities import Inventory, InventoryStatus


class StubInventoryRepo(InventoryRepository):
    def __init__(self, inventories: list[Inventory]) -> None:
        self._store = {inv.id: inv for inv in inventories}

    def save(self, inventory: Inventory) -> None:
        self._store[inventory.id] = inventory

    def get_by_id(self, inventory_id: str):
        return self._store.get(inventory_id)

    def list_all(self):
        return list(self._store.values())


def test_list_inventories_returns_all() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv1 = Inventory("id1", "A", InventoryStatus.DRAFT, now, now)
    inv2 = Inventory("id2", "B", InventoryStatus.PROCESSING, now, now)
    repo = StubInventoryRepo([inv1, inv2])
    use_case = ListInventoriesUseCase(inventory_repo=repo)

    result = use_case.execute()

    assert len(result) == 2
    ids = {r.id for r in result}
    assert ids == {"id1", "id2"}


def test_list_inventories_empty_when_none() -> None:
    repo = StubInventoryRepo([])
    use_case = ListInventoriesUseCase(inventory_repo=repo)

    result = use_case.execute()

    assert list(result) == []
