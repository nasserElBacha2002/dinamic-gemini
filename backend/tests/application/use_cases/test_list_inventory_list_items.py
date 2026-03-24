"""Tests for ListInventoryListItemsUseCase."""

from datetime import datetime, timezone

from src.application.ports.contracts import InventoryListItem
from src.application.use_cases.list_inventory_list_items import ListInventoryListItemsUseCase
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.positions.entities import Position, PositionStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository


def _inv(id_: str, name: str = "N") -> Inventory:
    now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    return Inventory(
        id=id_,
        name=name,
        status=InventoryStatus.DRAFT,
        created_at=now,
        updated_at=now,
    )


def _aisle(aid: str, inv_id: str) -> Aisle:
    now = datetime(2025, 1, 2, 12, 0, 0, tzinfo=timezone.utc)
    return Aisle(
        id=aid,
        inventory_id=inv_id,
        code="A1",
        status=AisleStatus.CREATED,
        created_at=now,
        updated_at=now,
    )


def _pos(pid: str, aisle_id: str, needs_review: bool) -> Position:
    now = datetime(2025, 1, 3, 12, 0, 0, tzinfo=timezone.utc)
    return Position(
        id=pid,
        aisle_id=aisle_id,
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=needs_review,
        primary_evidence_id=None,
        created_at=now,
        updated_at=now,
    )


def test_list_items_includes_counts_and_pending() -> None:
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    pos_repo = MemoryPositionRepository()
    i1 = _inv("inv-1")
    inv_repo.save(i1)
    a1 = _aisle("aisle-1", "inv-1")
    aisle_repo.save(a1)
    pos_repo.save(_pos("p1", "aisle-1", needs_review=True))
    pos_repo.save(_pos("p2", "aisle-1", needs_review=False))

    uc = ListInventoryListItemsUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        position_repo=pos_repo,
    )
    out = list(uc.execute())
    assert len(out) == 1
    row = out[0]
    assert isinstance(row, InventoryListItem)
    assert row.inventory.id == "inv-1"
    assert row.aisles_count == 1
    assert row.pending_review_count == 1


def test_list_items_empty_repos() -> None:
    uc = ListInventoryListItemsUseCase(
        inventory_repo=MemoryInventoryRepository(),
        aisle_repo=MemoryAisleRepository(),
        position_repo=MemoryPositionRepository(),
    )
    assert list(uc.execute()) == []
