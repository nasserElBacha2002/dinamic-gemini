"""Tests for GetInventoryUseCase."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from typing import Optional, Sequence

from src.application.errors import InventoryNotFoundError
from src.application.ports.repositories import InventoryRepository
from src.application.use_cases.get_inventory import GetInventoryUseCase
from src.domain.inventory.entities import Inventory, InventoryStatus


class StubInventoryRepo(InventoryRepository):
    def __init__(self) -> None:
        self._store: dict[str, Inventory] = {}

    def save(self, inventory: Inventory) -> None:
        self._store[inventory.id] = inventory

    def get_by_id(self, inventory_id: str) -> Optional[Inventory]:
        return self._store.get(inventory_id)

    def list_all(self) -> Sequence[Inventory]:
        return list(self._store.values())


def test_get_inventory_returns_entity_when_found() -> None:
    repo = StubInventoryRepo()
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory(
        id="inv-1",
        name="Test",
        status=InventoryStatus.DRAFT,
        created_at=now,
        updated_at=now,
    )
    repo.save(inv)

    use_case = GetInventoryUseCase(inventory_repo=repo)
    result = use_case.execute("inv-1")

    assert result is not None
    assert result.id == "inv-1"
    assert result.name == "Test"


def test_get_inventory_raises_when_not_found() -> None:
    repo = StubInventoryRepo()
    use_case = GetInventoryUseCase(inventory_repo=repo)
    with pytest.raises(InventoryNotFoundError):
        use_case.execute("nonexistent")
