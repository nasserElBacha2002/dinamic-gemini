"""Tests for ListInventoryListItemsUseCase."""

from datetime import datetime, timezone

from src.application.ports.contracts import InventoryListItem
from src.application.use_cases.inventories.list_inventory_list_items import ListInventoryListItemsUseCase
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.positions.entities import Position, PositionStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository

UTC = timezone.utc

T0 = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
T1 = datetime(2025, 1, 1, 11, 0, 0, tzinfo=UTC)
T2 = datetime(2025, 1, 2, 12, 0, 0, tzinfo=UTC)
T3 = datetime(2025, 1, 2, 15, 0, 0, tzinfo=UTC)
T4 = datetime(2025, 1, 3, 20, 0, 0, tzinfo=UTC)


def _inv(
    id_: str,
    name: str = "N",
    *,
    created_at: datetime = T0,
    updated_at: datetime = T1,
) -> Inventory:
    return Inventory(
        id=id_,
        name=name,
        status=InventoryStatus.DRAFT,
        created_at=created_at,
        updated_at=updated_at,
    )


def _aisle(aid: str, inv_id: str, *, created_at: datetime = T2, updated_at: datetime = T3) -> Aisle:
    return Aisle(
        id=aid,
        inventory_id=inv_id,
        code="A1",
        status=AisleStatus.CREATED,
        created_at=created_at,
        updated_at=updated_at,
    )


def _pos(
    pid: str,
    aisle_id: str,
    needs_review: bool,
    *,
    created_at: datetime = T3,
    updated_at: datetime = T4,
) -> Position:
    return Position(
        id=pid,
        aisle_id=aisle_id,
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=needs_review,
        primary_evidence_id=None,
        created_at=created_at,
        updated_at=updated_at,
    )


def test_list_items_includes_counts_and_pending() -> None:
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    pos_repo = MemoryPositionRepository()
    i1 = _inv("inv-1")
    inv_repo.save(i1)
    aisle_repo.save(_aisle("aisle-1", "inv-1"))
    pos_repo.save(_pos("p1", "aisle-1", needs_review=True))
    pos_repo.save(_pos("p2", "aisle-1", needs_review=False))

    uc = ListInventoryListItemsUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        position_repo=pos_repo,
    )
    out, total = uc.execute()
    assert total == 1
    assert len(out) == 1
    row = out[0]
    assert isinstance(row, InventoryListItem)
    assert row.inventory.id == "inv-1"
    assert row.aisles_count == 1
    assert row.pending_review_count == 1


def test_inventory_with_no_aisles_zero_counts_and_last_activity_from_inventory_only() -> None:
    """No aisles: counts zero; last_activity is max of inventory created_at/updated_at."""
    inv_repo = MemoryInventoryRepository()
    created = datetime(2025, 6, 1, 8, 0, 0, tzinfo=UTC)
    updated = datetime(2025, 6, 1, 18, 30, 0, tzinfo=UTC)
    inv_repo.save(_inv("inv-empty", created_at=created, updated_at=updated))

    uc = ListInventoryListItemsUseCase(
        inventory_repo=inv_repo,
        aisle_repo=MemoryAisleRepository(),
        position_repo=MemoryPositionRepository(),
    )
    row = uc.execute()[0][0]
    assert row.aisles_count == 0
    assert row.pending_review_count == 0
    assert row.last_activity_at == updated


def test_last_activity_at_is_max_across_inventory_aisle_and_position_times() -> None:
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    pos_repo = MemoryPositionRepository()

    inv = _inv(
        "inv-max",
        created_at=datetime(2025, 3, 1, 8, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 3, 1, 9, 0, 0, tzinfo=UTC),
    )
    inv_repo.save(inv)
    aisle_repo.save(
        _aisle(
            "aisle-max",
            "inv-max",
            created_at=datetime(2025, 3, 1, 10, 0, 0, tzinfo=UTC),
            updated_at=datetime(2025, 3, 1, 14, 0, 0, tzinfo=UTC),
        )
    )
    pos_repo.save(
        _pos(
            "p-max",
            "aisle-max",
            needs_review=False,
            created_at=datetime(2025, 3, 1, 15, 0, 0, tzinfo=UTC),
            updated_at=datetime(2025, 3, 1, 21, 0, 0, tzinfo=UTC),
        )
    )

    uc = ListInventoryListItemsUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        position_repo=pos_repo,
    )
    row = uc.execute()[0][0]
    assert row.last_activity_at == datetime(2025, 3, 1, 21, 0, 0, tzinfo=UTC)


def test_list_items_empty_repos() -> None:
    uc = ListInventoryListItemsUseCase(
        inventory_repo=MemoryInventoryRepository(),
        aisle_repo=MemoryAisleRepository(),
        position_repo=MemoryPositionRepository(),
    )
    items, total = uc.execute()
    assert items == [] and total == 0
