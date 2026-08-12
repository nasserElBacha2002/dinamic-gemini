"""Tests for SoftDeleteInventoriesUseCase."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.dto.access_principal import AccessPrincipal
from src.application.ports.repositories import InventoryRepository
from src.application.use_cases.inventories.get_inventory import GetInventoryUseCase
from src.application.use_cases.inventories.soft_delete_inventories import (
    SoftDeleteInventoriesCommand,
    SoftDeleteInventoriesUseCase,
)
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from tests.support.inventory_repository_cas import ExplicitInventoryCompareAndSet


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def _platform() -> AccessPrincipal:
    return AccessPrincipal(
        actor_id="admin",
        client_id=None,
        roles=frozenset({"platform_admin"}),
        is_platform=True,
    )


def _company(client_id: str = "client-a") -> AccessPrincipal:
    return AccessPrincipal(
        actor_id="user-1",
        client_id=client_id,
        roles=frozenset({"company_admin"}),
        is_platform=False,
    )


def _inv(
    inv_id: str,
    *,
    client_id: str | None = "client-a",
    deleted_at: datetime | None = None,
) -> Inventory:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return Inventory(
        id=inv_id,
        name=f"Inv {inv_id}",
        status=InventoryStatus.DRAFT,
        created_at=now,
        updated_at=now,
        client_id=client_id,
        deleted_at=deleted_at,
        deleted_by=None,
    )


@pytest.fixture
def repo() -> MemoryInventoryRepository:
    return MemoryInventoryRepository()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc))


def test_soft_delete_one(repo: MemoryInventoryRepository, clock: FixedClock) -> None:
    repo.save(_inv("i1"))
    uc = SoftDeleteInventoriesUseCase(repo, clock)
    result = uc.execute(
        SoftDeleteInventoriesCommand(inventory_ids=("i1",), principal=_platform())
    )
    assert result.deleted_ids == ("i1",)
    assert result.already_deleted_ids == ()
    assert result.not_found_ids == ()
    stored = repo.get_by_id("i1")
    assert stored is not None
    assert stored.deleted_at == clock.now()
    assert stored.deleted_by == "admin"
    assert repo.list_all() == []


def test_soft_delete_multiple(repo: MemoryInventoryRepository, clock: FixedClock) -> None:
    repo.save(_inv("i1"))
    repo.save(_inv("i2"))
    repo.save(_inv("i3"))
    uc = SoftDeleteInventoriesUseCase(repo, clock)
    result = uc.execute(
        SoftDeleteInventoriesCommand(inventory_ids=("i1", "i3"), principal=_platform())
    )
    assert set(result.deleted_ids) == {"i1", "i3"}
    assert [i.id for i in repo.list_all()] == ["i2"]


def test_soft_delete_already_deleted_idempotent(
    repo: MemoryInventoryRepository, clock: FixedClock
) -> None:
    first = clock.now()
    repo.save(_inv("i1", deleted_at=first))
    later = FixedClock(datetime(2026, 8, 12, 16, 0, tzinfo=timezone.utc))
    uc = SoftDeleteInventoriesUseCase(repo, later)
    result = uc.execute(
        SoftDeleteInventoriesCommand(inventory_ids=("i1",), principal=_platform())
    )
    assert result.deleted_ids == ()
    assert result.already_deleted_ids == ("i1",)
    stored = repo.get_by_id("i1")
    assert stored is not None
    assert stored.deleted_at == first


def test_soft_delete_missing_id(repo: MemoryInventoryRepository, clock: FixedClock) -> None:
    uc = SoftDeleteInventoriesUseCase(repo, clock)
    result = uc.execute(
        SoftDeleteInventoriesCommand(inventory_ids=("missing",), principal=_platform())
    )
    assert result.not_found_ids == ("missing",)
    assert result.deleted_ids == ()


def test_soft_delete_dedupes_ids(repo: MemoryInventoryRepository, clock: FixedClock) -> None:
    repo.save(_inv("i1"))
    uc = SoftDeleteInventoriesUseCase(repo, clock)
    result = uc.execute(
        SoftDeleteInventoriesCommand(inventory_ids=("i1", "i1", " i1 "), principal=_platform())
    )
    assert result.deleted_ids == ("i1",)


def test_soft_delete_empty_list_raises(repo: MemoryInventoryRepository, clock: FixedClock) -> None:
    uc = SoftDeleteInventoriesUseCase(repo, clock)
    with pytest.raises(ValueError, match="empty"):
        uc.execute(SoftDeleteInventoriesCommand(inventory_ids=(), principal=_platform()))


def test_soft_delete_other_client_scope(
    repo: MemoryInventoryRepository, clock: FixedClock
) -> None:
    repo.save(_inv("i1", client_id="client-a"))
    uc = SoftDeleteInventoriesUseCase(repo, clock)
    result = uc.execute(
        SoftDeleteInventoriesCommand(inventory_ids=("i1",), principal=_company("client-b"))
    )
    assert result.not_found_ids == ("i1",)
    assert repo.get_by_id("i1") is not None
    assert repo.get_by_id("i1").deleted_at is None  # type: ignore[union-attr]


def test_list_excludes_deleted(repo: MemoryInventoryRepository, clock: FixedClock) -> None:
    repo.save(_inv("alive"))
    repo.save(_inv("gone"))
    SoftDeleteInventoriesUseCase(repo, clock).execute(
        SoftDeleteInventoriesCommand(inventory_ids=("gone",), principal=_platform())
    )
    assert [i.id for i in repo.list_all()] == ["alive"]


def test_get_inventory_treats_deleted_as_not_found(
    repo: MemoryInventoryRepository, clock: FixedClock
) -> None:
    repo.save(_inv("i1"))
    SoftDeleteInventoriesUseCase(repo, clock).execute(
        SoftDeleteInventoriesCommand(inventory_ids=("i1",), principal=_platform())
    )
    from src.application.errors import InventoryNotFoundError

    with pytest.raises(InventoryNotFoundError):
        GetInventoryUseCase(repo).execute("i1")
    # Raw repo still holds the row (no physical delete).
    assert repo.get_by_id("i1") is not None
    assert repo.get_by_id("i1").is_deleted  # type: ignore[union-attr]


def test_soft_delete_preserves_related_entities_in_store(
    repo: MemoryInventoryRepository, clock: FixedClock
) -> None:
    """Soft delete only touches inventory row; dependents are not cascaded here."""
    repo.save(_inv("i1"))
    SoftDeleteInventoriesUseCase(repo, clock).execute(
        SoftDeleteInventoriesCommand(inventory_ids=("i1",), principal=_platform())
    )
    # Inventory still loadable from storage for in-flight workers.
    assert isinstance(repo.get_by_id("i1"), Inventory)


class StubListAllNoFilter(ExplicitInventoryCompareAndSet, InventoryRepository):
    """Legacy-style stub that does not filter deleted (ensures use-case still works)."""

    def __init__(self) -> None:
        self._store: dict[str, Inventory] = {}

    def save(self, inventory: Inventory) -> None:
        self._store[inventory.id] = inventory

    def get_by_id(self, inventory_id: str) -> Inventory | None:
        return self._store.get(inventory_id)

    def list_all(self):
        return list(self._store.values())
