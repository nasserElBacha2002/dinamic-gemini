"""Tests for ListInventoryListItemsUseCase (aggregates + client names + query budget)."""

from datetime import datetime, timezone

from src.application.ports.contracts import InventoryListItem, InventoryTableQuery
from src.application.use_cases.inventories.list_inventory_list_items import (
    ListInventoryListItemsUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.client.entities import Client, ClientStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.positions.entities import Position, PositionStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_client_repository import MemoryClientRepository
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
    client_id: str | None = None,
) -> Inventory:
    return Inventory(
        id=id_,
        name=name,
        status=InventoryStatus.DRAFT,
        created_at=created_at,
        updated_at=updated_at,
        client_id=client_id,
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


def _uc(
    inv_repo=None,
    aisle_repo=None,
    pos_repo=None,
    client_repo=None,
) -> ListInventoryListItemsUseCase:
    return ListInventoryListItemsUseCase(
        inventory_repo=inv_repo or MemoryInventoryRepository(),
        aisle_repo=aisle_repo or MemoryAisleRepository(),
        position_repo=pos_repo or MemoryPositionRepository(),
        client_repo=client_repo or MemoryClientRepository(),
    )


def test_list_items_includes_counts_and_pending() -> None:
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    pos_repo = MemoryPositionRepository()
    inv_repo.save(_inv("inv-1"))
    aisle_repo.save(_aisle("aisle-1", "inv-1"))
    pos_repo.save(_pos("p1", "aisle-1", needs_review=True))
    pos_repo.save(_pos("p2", "aisle-1", needs_review=False))

    out, total = _uc(inv_repo, aisle_repo, pos_repo).execute()
    assert total == 1
    assert len(out) == 1
    row = out[0]
    assert isinstance(row, InventoryListItem)
    assert row.inventory.id == "inv-1"
    assert row.aisles_count == 1
    assert row.pending_review_count == 1


def test_inventory_with_no_aisles_zero_counts_and_last_activity_from_inventory_only() -> None:
    inv_repo = MemoryInventoryRepository()
    created = datetime(2025, 6, 1, 8, 0, 0, tzinfo=UTC)
    updated = datetime(2025, 6, 1, 9, 0, 0, tzinfo=UTC)
    inv_repo.save(_inv("inv-empty", created_at=created, updated_at=updated))
    row = _uc(inv_repo).execute()[0][0]
    assert row.aisles_count == 0
    assert row.pending_review_count == 0
    assert row.last_activity_at == updated


def test_last_activity_uses_max_across_inventory_aisle_position() -> None:
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    pos_repo = MemoryPositionRepository()
    inv_repo.save(
        _inv(
            "inv-max",
            created_at=datetime(2025, 3, 1, 8, 0, 0, tzinfo=UTC),
            updated_at=datetime(2025, 3, 1, 9, 0, 0, tzinfo=UTC),
        )
    )
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
    row = _uc(inv_repo, aisle_repo, pos_repo).execute()[0][0]
    assert row.last_activity_at == datetime(2025, 3, 1, 21, 0, 0, tzinfo=UTC)


def test_list_items_empty_repos() -> None:
    items, total = _uc().execute()
    assert items == [] and total == 0


def test_list_items_resolves_client_name_null_and_missing_client() -> None:
    inv_repo = MemoryInventoryRepository()
    client_repo = MemoryClientRepository()
    client_repo.save(
        Client(
            id="c-1",
            name="Cliente Ejemplo",
            status=ClientStatus.ACTIVE,
            created_at=T0,
            updated_at=T0,
        )
    )
    inv_repo.save(_inv("inv-1", "With Client", client_id="c-1"))
    inv_repo.save(_inv("inv-2", "Legacy", client_id=None))
    inv_repo.save(_inv("inv-3", "Orphan", client_id="missing-client"))

    calls = {"n": 0}
    original = client_repo.get_by_ids

    def counting_get_by_ids(ids):
        calls["n"] += 1
        return original(ids)

    client_repo.get_by_ids = counting_get_by_ids  # type: ignore[method-assign]

    rows, total = _uc(inv_repo=inv_repo, client_repo=client_repo).execute()
    assert total == 3
    by_id = {r.inventory.id: r for r in rows}
    assert by_id["inv-1"].client_name == "Cliente Ejemplo"
    assert by_id["inv-2"].client_name is None
    assert by_id["inv-3"].client_name is None
    assert calls["n"] == 1


def test_entity_sort_paginates_before_aggregate_load_single_batch() -> None:
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    for i in range(5):
        inv_repo.save(_inv(f"inv-{i}", name=f"Inv {i}", client_id=None))
        aisle_repo.save(_aisle(f"a-{i}", f"inv-{i}"))

    calls = {"list_by_inventories": 0}
    original = aisle_repo.list_by_inventories

    def counting(ids):
        calls["list_by_inventories"] += 1
        return original(ids)

    aisle_repo.list_by_inventories = counting  # type: ignore[method-assign]

    rows, total = _uc(inv_repo=inv_repo, aisle_repo=aisle_repo).execute(
        InventoryTableQuery(sort_by="name", sort_dir="asc", page=2, page_size=2)
    )
    assert total == 5
    assert len(rows) == 2
    assert calls["list_by_inventories"] == 1
    assert {r.inventory.id for r in rows} == {"inv-2", "inv-3"}


def test_aggregate_sort_uses_one_list_by_inventories_call() -> None:
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    inv_repo.save(_inv("inv-a", "A"))
    inv_repo.save(_inv("inv-b", "B"))
    aisle_repo.save(_aisle("a1", "inv-b"))
    aisle_repo.save(_aisle("a2", "inv-b"))

    calls = {"n": 0}
    original = aisle_repo.list_by_inventories

    def counting(ids):
        calls["n"] += 1
        return original(ids)

    aisle_repo.list_by_inventories = counting  # type: ignore[method-assign]

    rows, total = _uc(inv_repo=inv_repo, aisle_repo=aisle_repo).execute(
        InventoryTableQuery(sort_by="aisles_count", sort_dir="desc", page=1, page_size=10)
    )
    assert total == 2
    assert rows[0].inventory.id == "inv-b"
    assert rows[0].aisles_count == 2
    assert calls["n"] == 1
