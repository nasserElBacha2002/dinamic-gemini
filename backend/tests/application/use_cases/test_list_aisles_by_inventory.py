"""Tests for ListAislesByInventoryUseCase."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

import pytest

from src.application.ports.repositories import AisleRepository, InventoryRepository
from src.application.use_cases.create_aisle import InventoryNotFoundError
from src.application.use_cases.list_aisles_by_inventory import ListAislesByInventoryUseCase
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus


class StubInventoryRepo(InventoryRepository):
    def __init__(self, inventory_ids: set[str] | None = None) -> None:
        self._ids = inventory_ids or set()

    def save(self, inventory: Inventory) -> None:
        self._ids.add(inventory.id)

    def get_by_id(self, inventory_id: str) -> Inventory | None:
        if inventory_id in self._ids:
            now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
            return Inventory(inventory_id, "Stub", InventoryStatus.DRAFT, now, now)
        return None

    def list_all(self) -> Sequence[Inventory]:
        return []


class StubAisleRepo(AisleRepository):
    def __init__(self, aisles: list[Aisle] | None = None) -> None:
        self._store = {a.id: a for a in (aisles or [])}

    def save(self, aisle: Aisle) -> None:
        self._store[aisle.id] = aisle

    def get_by_id(self, aisle_id: str) -> Aisle | None:
        return self._store.get(aisle_id)

    def list_by_inventory(self, inventory_id: str) -> Sequence[Aisle]:
        return [a for a in self._store.values() if a.inventory_id == inventory_id]

    def get_by_inventory_and_code(self, inventory_id: str, code: str) -> Aisle | None:
        for a in self._store.values():
            if a.inventory_id == inventory_id and a.code == code:
                return a
        return None


def test_list_aisles_returns_all_for_inventory() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    a1 = Aisle("a1", "inv-1", "A-01", AisleStatus.CREATED, now, now)
    a2 = Aisle("a2", "inv-1", "A-02", AisleStatus.CREATED, now, now)
    a3 = Aisle("a3", "inv-2", "B-01", AisleStatus.CREATED, now, now)
    inv_repo = StubInventoryRepo({"inv-1", "inv-2"})
    aisle_repo = StubAisleRepo([a1, a2, a3])
    use_case = ListAislesByInventoryUseCase(inventory_repo=inv_repo, aisle_repo=aisle_repo)

    result = use_case.execute("inv-1")

    assert len(result) == 2
    codes = {r.code for r in result}
    assert codes == {"A-01", "A-02"}


def test_list_aisles_empty_when_none() -> None:
    inv_repo = StubInventoryRepo({"inv-1"})
    aisle_repo = StubAisleRepo([])
    use_case = ListAislesByInventoryUseCase(inventory_repo=inv_repo, aisle_repo=aisle_repo)

    result = use_case.execute("inv-1")

    assert list(result) == []


def test_list_aisles_raises_when_inventory_not_found() -> None:
    inv_repo = StubInventoryRepo(set())
    aisle_repo = StubAisleRepo([])
    use_case = ListAislesByInventoryUseCase(inventory_repo=inv_repo, aisle_repo=aisle_repo)

    with pytest.raises(InventoryNotFoundError):
        use_case.execute("nonexistent")
