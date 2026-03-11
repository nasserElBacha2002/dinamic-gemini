"""Tests for CreateInventoryUseCase."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.ports.repositories import InventoryRepository
from src.application.use_cases.create_inventory import CreateInventoryCommand, CreateInventoryUseCase
from src.domain.inventory.entities import Inventory, InventoryStatus


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class StubInventoryRepo(InventoryRepository):
    def __init__(self) -> None:
        self._store: dict[str, Inventory] = {}

    def save(self, inventory: Inventory) -> None:
        self._store[inventory.id] = inventory

    def get_by_id(self, inventory_id: str):
        return self._store.get(inventory_id)

    def list_all(self):
        return list(self._store.values())


def test_create_inventory_persists_and_returns_entity() -> None:
    repo = StubInventoryRepo()
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    clock = FixedClock(now)
    use_case = CreateInventoryUseCase(inventory_repo=repo, clock=clock)

    result = use_case.execute(CreateInventoryCommand(name="Warehouse A"))

    assert result.name == "Warehouse A"
    assert result.status == InventoryStatus.DRAFT
    assert result.created_at == now
    assert result.updated_at == now
    assert repo.get_by_id(result.id) == result
    assert len(repo.list_all()) == 1
