"""Tests for UpdateInventoryNameUseCase."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

import pytest

from src.application.errors import InventoryNotFoundError
from src.application.ports.repositories import InventoryRepository
from src.application.services.optional_unset import UNSET
from src.application.use_cases.inventories.update_inventory_name import (
    UpdateInventoryNameCommand,
    UpdateInventoryNameUseCase,
)
from src.domain.aisle_identification.modes import AisleIdentificationMode
from src.domain.inventory.entities import Inventory, InventoryStatus


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class StubInventoryRepo(InventoryRepository):
    def __init__(self, inventories: list[Inventory] | None = None) -> None:
        self._store = {i.id: i for i in (inventories or [])}
        self.save_calls = 0

    def save(self, inventory: Inventory) -> None:
        self.save_calls += 1
        self._store[inventory.id] = inventory

    def get_by_id(self, inventory_id: str) -> Inventory | None:
        return self._store.get(inventory_id)

    def list_all(self) -> Sequence[Inventory]:
        return list(self._store.values())


def test_update_inventory_name_success() -> None:
    created = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    now = datetime(2025, 3, 7, 8, 0, 0, tzinfo=timezone.utc)
    inv = Inventory(
        id="inv-1",
        name="Old Name",
        status=InventoryStatus.DRAFT,
        created_at=created,
        updated_at=created,
    )
    repo = StubInventoryRepo([inv])
    uc = UpdateInventoryNameUseCase(inventory_repo=repo, clock=FixedClock(now))

    result = uc.execute(UpdateInventoryNameCommand(inventory_id="inv-1", name="  New Name  "))

    assert result.name == "New Name"
    assert result.updated_at == now
    assert repo.save_calls == 1


def test_update_inventory_name_rejects_empty() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv-1", "Warehouse", InventoryStatus.DRAFT, now, now)
    repo = StubInventoryRepo([inv])
    uc = UpdateInventoryNameUseCase(inventory_repo=repo, clock=FixedClock(now))

    with pytest.raises(ValueError, match="must not be empty"):
        uc.execute(UpdateInventoryNameCommand(inventory_id="inv-1", name="   "))
    assert repo.save_calls == 0


def test_update_inventory_name_noop_when_unchanged() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv-1", "Warehouse", InventoryStatus.DRAFT, now, now)
    repo = StubInventoryRepo([inv])
    later = datetime(2025, 3, 8, 1, 0, 0, tzinfo=timezone.utc)
    uc = UpdateInventoryNameUseCase(inventory_repo=repo, clock=FixedClock(later))

    result = uc.execute(UpdateInventoryNameCommand(inventory_id="inv-1", name="  Warehouse  "))

    assert result.name == "Warehouse"
    assert result.updated_at == now
    assert repo.save_calls == 0


def test_update_inventory_name_not_found() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    uc = UpdateInventoryNameUseCase(inventory_repo=StubInventoryRepo(), clock=FixedClock(now))

    with pytest.raises(InventoryNotFoundError):
        uc.execute(UpdateInventoryNameCommand(inventory_id="missing", name="X"))


def test_update_inventory_partial_patch_identification_mode_only_leaves_name_unchanged() -> None:
    """Partial PATCH: omitting ``name`` must not require it (identification_mode alone is enough)."""
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv-1", "Warehouse", InventoryStatus.DRAFT, now, now)
    repo = StubInventoryRepo([inv])

    uc = UpdateInventoryNameUseCase(inventory_repo=repo, clock=FixedClock(now))
    result = uc.execute(
        UpdateInventoryNameCommand(
            inventory_id="inv-1", name=None, identification_mode=AisleIdentificationMode.CODE_SCAN
        )
    )

    assert result.name == "Warehouse"
    assert result.identification_mode == AisleIdentificationMode.CODE_SCAN
    assert repo.save_calls == 1


def test_update_inventory_partial_patch_explicit_null_clears_identification_mode() -> None:
    """Explicit ``identification_mode=None`` clears the inventory override (inherit from client)."""
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory(
        "inv-1",
        "Warehouse",
        InventoryStatus.DRAFT,
        now,
        now,
        identification_mode=AisleIdentificationMode.INTERNAL_OCR,
    )
    repo = StubInventoryRepo([inv])

    uc = UpdateInventoryNameUseCase(inventory_repo=repo, clock=FixedClock(now))
    result = uc.execute(UpdateInventoryNameCommand(inventory_id="inv-1", name=None, identification_mode=None))

    assert result.identification_mode is None
    assert repo.save_calls == 1


def test_update_inventory_partial_patch_unset_identification_mode_is_noop_field() -> None:
    """Default ``UNSET`` identification_mode leaves the stored override untouched."""
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory(
        "inv-1",
        "Warehouse",
        InventoryStatus.DRAFT,
        now,
        now,
        identification_mode=AisleIdentificationMode.INTERNAL_OCR,
    )
    repo = StubInventoryRepo([inv])

    uc = UpdateInventoryNameUseCase(inventory_repo=repo, clock=FixedClock(now))
    result = uc.execute(UpdateInventoryNameCommand(inventory_id="inv-1", name="New Warehouse"))

    assert result.identification_mode == AisleIdentificationMode.INTERNAL_OCR
    assert UpdateInventoryNameCommand(inventory_id="inv-1", name="x").identification_mode is UNSET


def test_update_inventory_partial_patch_requires_at_least_one_field() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv-1", "Warehouse", InventoryStatus.DRAFT, now, now)
    repo = StubInventoryRepo([inv])
    uc = UpdateInventoryNameUseCase(inventory_repo=repo, clock=FixedClock(now))

    with pytest.raises(ValueError, match="At least one field must be provided"):
        uc.execute(UpdateInventoryNameCommand(inventory_id="inv-1"))
    assert repo.save_calls == 0


def test_update_inventory_partial_patch_invalid_identification_mode_raises() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv-1", "Warehouse", InventoryStatus.DRAFT, now, now)
    repo = StubInventoryRepo([inv])
    uc = UpdateInventoryNameUseCase(inventory_repo=repo, clock=FixedClock(now))

    with pytest.raises(ValueError, match="Invalid identification_mode"):
        uc.execute(UpdateInventoryNameCommand(inventory_id="inv-1", identification_mode="AUTO"))
    assert repo.save_calls == 0
