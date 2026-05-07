"""Tests for CreateAisleUseCase."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

import pytest

from src.application.ports.repositories import AisleRepository, InventoryRepository
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.use_cases.create_aisle import (
    CreateAisleCommand,
    CreateAisleUseCase,
    DuplicateAisleCodeError,
    InventoryNotFoundError,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class StubInventoryRepo(InventoryRepository):
    def __init__(self, inventories: list[Inventory] | None = None) -> None:
        self._store = {i.id: i for i in (inventories or [])}

    def save(self, inventory: Inventory) -> None:
        self._store[inventory.id] = inventory

    def get_by_id(self, inventory_id: str) -> Inventory | None:
        return self._store.get(inventory_id)

    def list_all(self) -> Sequence[Inventory]:
        return list(self._store.values())


class StubAisleRepo(AisleRepository):
    def __init__(self) -> None:
        self._store: dict[str, Aisle] = {}

    def save(self, aisle: Aisle) -> None:
        self._store[aisle.id] = aisle

    def get_by_id(self, aisle_id: str) -> Aisle | None:
        return self._store.get(aisle_id)

    def list_by_inventory(self, inventory_id: str) -> Sequence[Aisle]:
        return [a for a in self._store.values() if a.inventory_id == inventory_id]

    def get_by_inventory_and_code(self, inventory_id: str, code: str) -> Aisle | None:
        for a in self._store.values():
            if a.inventory_id == inventory_id and a.code == code.strip():
                return a
        return None


def test_create_aisle_persists_and_returns_entity() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv-1", "Warehouse", InventoryStatus.DRAFT, now, now)
    inv_repo = StubInventoryRepo([inv])
    aisle_repo = StubAisleRepo()
    clock = FixedClock(now)

    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)
    use_case = CreateAisleUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        clock=clock,
        status_reconciler=reconciler,
    )
    result = use_case.execute(CreateAisleCommand(inventory_id="inv-1", code="A-01"))

    assert result.inventory_id == "inv-1"
    assert result.code == "A-01"
    assert result.status == AisleStatus.CREATED
    assert result.created_at == now
    assert result.client_supplier_id is None
    assert aisle_repo.get_by_id(result.id) == result
    assert len(aisle_repo.list_by_inventory("inv-1")) == 1
    updated_inv = inv_repo.get_by_id("inv-1")
    assert updated_inv is not None
    assert updated_inv.status != InventoryStatus.DRAFT


def test_create_aisle_raises_when_inventory_not_found() -> None:
    aisle_repo = StubAisleRepo()
    inv_repo = StubInventoryRepo([])  # no inventories
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock(now))
    use_case = CreateAisleUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        clock=FixedClock(now),
        status_reconciler=reconciler,
    )

    with pytest.raises(InventoryNotFoundError):
        use_case.execute(CreateAisleCommand(inventory_id="nonexistent", code="A-01"))


def test_create_aisle_raises_when_duplicate_code() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv-1", "Warehouse", InventoryStatus.DRAFT, now, now)
    existing = Aisle("a1", "inv-1", "A-01", AisleStatus.CREATED, now, now)
    inv_repo = StubInventoryRepo([inv])
    aisle_repo = StubAisleRepo()
    aisle_repo.save(existing)

    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock(now))
    use_case = CreateAisleUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        clock=FixedClock(now),
        status_reconciler=reconciler,
    )

    with pytest.raises(DuplicateAisleCodeError):
        use_case.execute(CreateAisleCommand(inventory_id="inv-1", code="A-01"))


def test_create_aisle_normalizes_code_for_duplicate_check_and_entity() -> None:
    """Code is normalized once; duplicate check and stored entity use same value."""
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv-1", "Warehouse", InventoryStatus.DRAFT, now, now)
    inv_repo = StubInventoryRepo([inv])
    aisle_repo = StubAisleRepo()
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock(now))
    use_case = CreateAisleUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        clock=FixedClock(now),
        status_reconciler=reconciler,
    )

    result = use_case.execute(CreateAisleCommand(inventory_id="inv-1", code=" A-01 "))
    assert result.code == "A-01"

    with pytest.raises(DuplicateAisleCodeError):
        use_case.execute(CreateAisleCommand(inventory_id="inv-1", code="A-01"))
