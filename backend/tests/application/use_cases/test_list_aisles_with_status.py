"""Tests for ListAislesWithStatusUseCase (batch job loading, no N+1)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional, Sequence

import pytest

from src.application.ports.contracts import AisleAssetRollup
from src.application.use_cases.list_aisles_with_status import ListAislesWithStatusUseCase
from src.application.use_cases.create_aisle import InventoryNotFoundError
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    JobRepository,
    PositionRepository,
    SourceAssetRepository,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.assets.entities import SourceAsset
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.domain.positions.entities import Position, PositionStatus


class StubInventoryRepo(InventoryRepository):
    def __init__(self, inventory_ids: set[str] | None = None) -> None:
        self._ids = inventory_ids or set()

    def save(self, inventory: Inventory) -> None:
        self._ids.add(inventory.id)

    def get_by_id(self, inventory_id: str) -> Optional[Inventory]:
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

    def get_by_id(self, aisle_id: str) -> Optional[Aisle]:
        return self._store.get(aisle_id)

    def list_by_inventory(self, inventory_id: str) -> Sequence[Aisle]:
        return [a for a in self._store.values() if a.inventory_id == inventory_id]

    def get_by_inventory_and_code(self, inventory_id: str, code: str) -> Optional[Aisle]:
        for a in self._store.values():
            if a.inventory_id == inventory_id and a.code == code:
                return a
        return None


class StubJobRepo(JobRepository):
    def __init__(self, latest_by_aisle: Dict[str, Job] | None = None) -> None:
        self._latest = latest_by_aisle or {}

    def save(self, job: Job) -> None:
        pass

    def get_by_id(self, job_id: str) -> Optional[Job]:
        return None

    def get_latest_by_target(self, target_type: str, target_id: str) -> Optional[Job]:
        if target_type != "aisle":
            return None
        return self._latest.get(target_id)

    def get_latest_by_targets(
        self, target_type: str, target_ids: Sequence[str]
    ) -> Dict[str, Job]:
        if target_type != "aisle":
            return {}
        return {tid: self._latest[tid] for tid in target_ids if tid in self._latest}


class StubPositionRepo(PositionRepository):
    def __init__(self, positions: list[Position] | None = None) -> None:
        self._positions = positions or []

    def save(self, position: Position) -> None:
        self._positions.append(position)

    def get_by_id(self, position_id: str) -> Optional[Position]:
        for p in self._positions:
            if p.id == position_id:
                return p
        return None

    def list_by_aisle(
        self,
        aisle_id: str,
        status: Optional[str] = None,
        needs_review: Optional[bool] = None,
        min_confidence: Optional[float] = None,
        sku_filter: Optional[str] = None,
        page: int = 1,
        page_size: int = 25,
    ) -> Sequence[Position]:
        return [p for p in self._positions if p.aisle_id == aisle_id]

    def list_by_aisle_query(self, aisle_id: str, query=None) -> Sequence[Position]:
        return self.list_by_aisle(aisle_id)

    def list_by_aisles(self, aisle_ids: Sequence[str]) -> Sequence[Position]:
        want = set(aisle_ids)
        return [p for p in self._positions if p.aisle_id in want]


class StubSourceAssetRepo(SourceAssetRepository):
    """Returns canned rollups for requested aisle ids (empty when unknown)."""

    def __init__(self, rollup_by_aisle: Dict[str, AisleAssetRollup] | None = None) -> None:
        self._rollup = rollup_by_aisle or {}

    def save(self, asset: SourceAsset) -> None:
        pass

    def get_by_id(self, asset_id: str) -> Optional[SourceAsset]:
        return None

    def list_by_aisle(self, aisle_id: str) -> Sequence[SourceAsset]:
        return []

    def summarize_assets_for_aisles(self, aisle_ids: Sequence[str]) -> Dict[str, AisleAssetRollup]:
        return {aid: self._rollup[aid] for aid in aisle_ids if aid in self._rollup}


def test_list_aisles_with_status_returns_aisles_and_latest_jobs() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    a1 = Aisle("a1", "inv-1", "A-01", AisleStatus.CREATED, now, now)
    a2 = Aisle("a2", "inv-1", "A-02", AisleStatus.CREATED, now, now)
    j1 = Job(
        "j1",
        "aisle",
        "a1",
        "process_aisle",
        JobStatus.RUNNING,
        {},
        now,
        now,
    )
    inv_repo = StubInventoryRepo({"inv-1"})
    aisle_repo = StubAisleRepo([a1, a2])
    job_repo = StubJobRepo({"a1": j1})

    use_case = ListAislesWithStatusUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        position_repo=StubPositionRepo([]),
        source_asset_repo=StubSourceAssetRepo({}),
    )
    result = use_case.execute("inv-1")

    assert len(result) == 2
    by_id = {r.aisle.id: r for r in result}
    assert by_id["a1"].latest_job is not None
    assert by_id["a1"].latest_job.id == "j1"
    assert by_id["a2"].latest_job is None
    assert by_id["a1"].assets_count == 0
    assert by_id["a1"].positions_count == 0
    assert by_id["a1"].pending_review_positions_count == 0


def test_list_aisles_with_status_rollups_positions_and_pending_review() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    later = datetime(2025, 3, 7, 12, 0, 0, tzinfo=timezone.utc)
    a1 = Aisle("a1", "inv-1", "A-01", AisleStatus.CREATED, now, now)
    p1 = Position(
        "p1",
        "a1",
        PositionStatus.DETECTED,
        0.9,
        True,
        None,
        now,
        later,
    )
    p2 = Position(
        "p2",
        "a1",
        PositionStatus.DETECTED,
        0.9,
        False,
        None,
        now,
        now,
    )
    inv_repo = StubInventoryRepo({"inv-1"})
    aisle_repo = StubAisleRepo([a1])
    job_repo = StubJobRepo({})
    pos_repo = StubPositionRepo([p1, p2])
    asset_roll = AisleAssetRollup(count=3, last_uploaded_at=later)
    src_repo = StubSourceAssetRepo({"a1": asset_roll})

    use_case = ListAislesWithStatusUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        position_repo=pos_repo,
        source_asset_repo=src_repo,
    )
    result = use_case.execute("inv-1")
    assert len(result) == 1
    row = result[0]
    assert row.assets_count == 3
    assert row.positions_count == 2
    assert row.pending_review_positions_count == 1
    assert row.last_activity_at == max(now, later, later, later)


def test_list_aisles_with_status_raises_when_inventory_not_found() -> None:
    inv_repo = StubInventoryRepo(set())
    aisle_repo = StubAisleRepo([])
    job_repo = StubJobRepo()
    use_case = ListAislesWithStatusUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        position_repo=StubPositionRepo([]),
        source_asset_repo=StubSourceAssetRepo({}),
    )

    with pytest.raises(InventoryNotFoundError):
        use_case.execute("nonexistent")
