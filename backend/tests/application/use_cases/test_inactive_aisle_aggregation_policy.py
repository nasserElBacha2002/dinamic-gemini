"""Inactive aisle aggregation policy — operational qty vs historical cost/status.

Fixture I1:
- Aisle A active with operational qty 100
- Aisle B inactive with historical qty 50
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from src.application.ports.contracts import PositionListQuery
from src.application.ports.repositories import AisleRepository, PositionRepository
from src.application.services.export_inventory_collector import ExportInventoryCollector
from src.application.services.inventory_aggregation_scope import scope_from_aisles
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.services.result_context_resolver import ResultContextResolver
from src.application.use_cases.inventories.list_inventory_list_items import (
    ListInventoryListItemsUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.positions.entities import Position, PositionStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_product_record_repository import (
    MemoryProductRecordRepository,
)
from src.infrastructure.services.inventory_metrics_service import InventoryMetricsService

NOW = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def _inventory() -> Inventory:
    return Inventory(
        id="I1",
        name="Inv 1",
        status=InventoryStatus.IN_REVIEW,
        created_at=NOW,
        updated_at=NOW,
    )


def _aisle(
    aid: str,
    *,
    code: str,
    is_active: bool = True,
    status: AisleStatus = AisleStatus.COMPLETED,
) -> Aisle:
    return Aisle(
        id=aid,
        inventory_id="I1",
        code=code,
        status=status,
        created_at=NOW,
        updated_at=NOW,
        is_active=is_active,
    )


def _position(pid: str, aisle_id: str, qty: int, *, needs_review: bool = False) -> Position:
    return Position(
        id=pid,
        aisle_id=aisle_id,
        status=PositionStatus.REVIEWED,
        confidence=0.95,
        needs_review=needs_review,
        primary_evidence_id=None,
        created_at=NOW,
        updated_at=NOW,
        detected_summary_json={"internal_code": f"SKU-{pid}", "final_quantity": qty},
    )


def _seed_i1(
    *,
    aisle_repo: MemoryAisleRepository,
    pos_repo: MemoryPositionRepository,
    inv_repo: MemoryInventoryRepository | None = None,
    b_status: AisleStatus = AisleStatus.FAILED,
) -> None:
    if inv_repo is not None:
        inv_repo.save(_inventory())
    aisle_repo.save(_aisle("A", code="A", is_active=True, status=AisleStatus.COMPLETED))
    aisle_repo.save(_aisle("B", code="B", is_active=False, status=b_status))
    pos_repo.save(_position("p-a", "A", 100))
    pos_repo.save(_position("p-b", "B", 50, needs_review=True))


def test_scope_fixture_i1() -> None:
    aisle_repo = MemoryAisleRepository()
    pos_repo = MemoryPositionRepository()
    _seed_i1(aisle_repo=aisle_repo, pos_repo=pos_repo)
    scope = scope_from_aisles(aisle_repo.list_by_inventory("I1"))
    assert scope.active_aisle_ids == frozenset({"A"})
    assert scope.all_aisle_ids == frozenset({"A", "B"})


def test_metrics_positions_only_from_active_aisle() -> None:
    aisle_repo = MemoryAisleRepository()
    pos_repo = MemoryPositionRepository()
    _seed_i1(aisle_repo=aisle_repo, pos_repo=pos_repo)

    result = InventoryMetricsService(aisle_repo, pos_repo).calculate_inventory_metrics("I1")

    assert result["total_positions"] == 1
    assert result["total_reviewed_positions"] == 1
    assert result["auto_accepted_positions"] == 1


def test_status_reconciler_ignores_inactive_failed_aisle() -> None:
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    pos_repo = MemoryPositionRepository()
    _seed_i1(aisle_repo=aisle_repo, pos_repo=pos_repo, inv_repo=inv_repo, b_status=AisleStatus.FAILED)

    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock(NOW))
    changed = reconciler.reconcile("I1")
    inv = inv_repo.get_by_id("I1")
    assert inv is not None
    # Active aisle A is COMPLETED → inventory COMPLETED; inactive FAILED B ignored.
    assert inv.status == InventoryStatus.COMPLETED
    assert changed is True


def test_status_reconciler_no_active_aisles_is_draft() -> None:
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    inv_repo.save(_inventory())
    aisle_repo.save(_aisle("B", code="B", is_active=False, status=AisleStatus.FAILED))

    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock(NOW))
    reconciler.reconcile("I1")
    inv = inv_repo.get_by_id("I1")
    assert inv is not None
    assert inv.status == InventoryStatus.DRAFT


def test_export_collector_operational_only_filters_inactive() -> None:
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    pos_repo = MemoryPositionRepository()
    prod_repo = MemoryProductRecordRepository()
    job_repo = MemoryJobRepository()
    _seed_i1(aisle_repo=aisle_repo, pos_repo=pos_repo, inv_repo=inv_repo)

    collector = ExportInventoryCollector(
        inv_repo,
        aisle_repo,
        pos_repo,
        prod_repo,
        ResultContextResolver(job_repo, pos_repo),
    )
    ops = collector.collect_inventory("I1", operational_only=True)
    assert [a.id for a in ops.aisles_in_order] == ["A"]
    assert len(ops.aisle_bundles) == 1

    all_data = collector.collect_inventory("I1", operational_only=False)
    assert {a.id for a in all_data.aisles_in_order} == {"A", "B"}
    assert len(all_data.aisle_bundles) == 2


def test_list_items_pending_active_only_aisles_count_all() -> None:
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    pos_repo = MemoryPositionRepository()
    _seed_i1(aisle_repo=aisle_repo, pos_repo=pos_repo, inv_repo=inv_repo)

    uc = ListInventoryListItemsUseCase(inv_repo, aisle_repo, pos_repo)
    rows, total = uc.execute()
    assert total == 1
    row = rows[0]
    assert row.aisles_count == 2
    # Pending on inactive B must not count.
    assert row.pending_review_count == 0


class StubAisleRepo(AisleRepository):
    """Minimal stub used by metrics tests; defaults is_active=True on entities."""

    def __init__(self, aisles: list[Aisle]) -> None:
        self._aisles = aisles

    def save(self, aisle: Aisle) -> None:
        raise NotImplementedError

    def get_by_id(self, aisle_id: str) -> Aisle | None:
        for a in self._aisles:
            if a.id == aisle_id:
                return a
        return None

    def list_by_inventory(self, inventory_id: str) -> Sequence[Aisle]:
        return [a for a in self._aisles if a.inventory_id == inventory_id]

    def get_by_inventory_and_code(self, inventory_id: str, code: str) -> Aisle | None:
        for a in self._aisles:
            if a.inventory_id == inventory_id and a.code == code:
                return a
        return None


class StubPositionRepo(PositionRepository):
    def __init__(self, positions: list[Position]) -> None:
        self._positions = positions

    def save(self, position: Position) -> None:
        raise NotImplementedError

    def get_by_id(self, position_id: str) -> Position | None:
        for p in self._positions:
            if p.id == position_id:
                return p
        return None

    def list_by_aisle(
        self,
        aisle_id: str,
        status: str | None = None,
        needs_review: bool | None = None,
        min_confidence: float | None = None,
        sku_filter: str | None = None,
        page: int = 1,
        page_size: int = 25,
        sort_by: str = "created_at",
        sort_dir: str = "asc",
    ) -> Sequence[Position]:
        return []

    def list_by_aisle_query(
        self, aisle_id: str, query: PositionListQuery | None = None
    ) -> Sequence[Position]:
        return []

    def list_by_aisles(self, aisle_ids: Sequence[str]) -> Sequence[Position]:
        aid_set = set(aisle_ids)
        return [p for p in self._positions if p.aisle_id in aid_set]


def test_metrics_stub_aisle_default_is_active() -> None:
    """StubAisle / Aisle default is_active=True must keep existing metrics tests valid."""
    aisle = Aisle("a1", "inv-1", "A01", AisleStatus.CREATED, NOW, NOW)
    assert aisle.is_active is True
    positions = [
        Position(
            id="p1",
            aisle_id="a1",
            status=PositionStatus.REVIEWED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=NOW,
            updated_at=NOW,
        )
    ]
    service = InventoryMetricsService(StubAisleRepo([aisle]), StubPositionRepo(positions))
    result = service.calculate_inventory_metrics("inv-1")
    assert result["total_positions"] == 1
