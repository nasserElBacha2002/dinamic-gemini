"""Tests for ListAislesWithStatusUseCase (batch job loading, no N+1)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

import pytest

from src.application.ports.contracts import (
    POSITION_LIST_JOB_ID_UNSET,
    AisleAssetRollup,
    PositionListQuery,
)
from src.application.ports.repositories import (
    JOB_ID_FILTER_UNSET,
    AisleRepository,
    InventoryRepository,
    JobRepository,
    PositionRepository,
    SourceAssetRepository,
)
from src.application.services.result_context_resolver import ResultContextResolver
from src.application.use_cases.aisles.create_aisle import InventoryNotFoundError
from src.application.use_cases.aisles.list_aisles_with_status import ListAislesWithStatusUseCase
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.assets.entities import SourceAsset
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.domain.positions.entities import Position, PositionStatus
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from tests.support.job_repository_list_helpers import list_jobs_for_targets_from_store


class StubInventoryRepo(InventoryRepository):
    def __init__(self, inventory_ids: set[str] | None = None) -> None:
        self._ids = inventory_ids or set()

    def save(self, inventory: Inventory) -> None:
        self._ids.add(inventory.id)

    def get_by_id(self, inventory_id: str) -> Inventory | None:
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

    def get_by_id(self, aisle_id: str) -> Aisle | None:
        return self._store.get(aisle_id)

    def list_by_inventory(self, inventory_id: str) -> Sequence[Aisle]:
        return [a for a in self._store.values() if a.inventory_id == inventory_id]

    def get_by_inventory_and_code(self, inventory_id: str, code: str) -> Aisle | None:
        for a in self._store.values():
            if a.inventory_id == inventory_id and a.code == code:
                return a
        return None


class StubJobRepo(JobRepository):
    def __init__(self, latest_by_aisle: dict[str, Job] | None = None) -> None:
        self._latest = latest_by_aisle or {}

    def save(self, job: Job) -> None:
        pass

    def get_by_id(self, job_id: str) -> Job | None:
        return None

    def get_latest_by_target(self, target_type: str, target_id: str) -> Job | None:
        if target_type != "aisle":
            return None
        return self._latest.get(target_id)

    def get_latest_by_targets(self, target_type: str, target_ids: Sequence[str]) -> dict[str, Job]:
        if target_type != "aisle":
            return {}
        return {tid: self._latest[tid] for tid in target_ids if tid in self._latest}

    def list_jobs_for_target(
        self, target_type: str, target_id: str, *, limit: int = 50
    ) -> Sequence[Job]:
        if target_type != "aisle":
            return []
        j = self._latest.get(target_id)
        return [j] if j is not None else []



    def list_jobs_for_targets(
        self,
        target_type: str,
        target_ids: Sequence[str],
        *,
        job_type: str | None = None,
    ) -> Sequence[Job]:
        store = getattr(self, "_store", None) or getattr(self, "_jobs", None)
        if store is None:
            return []
        return list_jobs_for_targets_from_store(
            store, target_type, target_ids, job_type=job_type
        )


class StubPositionRepo(PositionRepository):
    def __init__(self, positions: list[Position] | None = None) -> None:
        self._positions = positions or []

    def save(self, position: Position) -> None:
        self._positions.append(position)

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
        job_id: str | None | object = JOB_ID_FILTER_UNSET,
    ) -> Sequence[Position]:
        positions = [p for p in self._positions if p.aisle_id == aisle_id]
        if job_id is not JOB_ID_FILTER_UNSET:
            if job_id is None:
                positions = [p for p in positions if p.job_id is None]
            else:
                positions = [p for p in positions if p.job_id == job_id]
        if status is not None:
            positions = [p for p in positions if p.status.value == status]
        if needs_review is not None:
            positions = [p for p in positions if p.needs_review == needs_review]
        if min_confidence is not None:
            positions = [p for p in positions if p.confidence >= min_confidence]
        sb = (sort_by or "created_at").strip().lower()
        reverse = (sort_dir or "asc").strip().lower() == "desc"

        def _key(p: Position) -> tuple:
            if sb == "updated_at":
                return (p.updated_at, p.id)
            if sb == "confidence":
                return (p.confidence, p.id)
            if sb == "id":
                return (p.id,)
            return (p.created_at, p.id)

        positions = sorted(positions, key=_key, reverse=reverse)
        start = (page - 1) * page_size
        return positions[start : start + page_size]

    def list_by_aisle_query(
        self, aisle_id: str, query: PositionListQuery | None = None
    ) -> Sequence[Position]:
        q = query or PositionListQuery()
        repo_job_id: str | None | object = JOB_ID_FILTER_UNSET
        if q.job_id is not POSITION_LIST_JOB_ID_UNSET:
            repo_job_id = q.job_id
        return self.list_by_aisle(
            aisle_id,
            status=q.status,
            needs_review=q.needs_review,
            min_confidence=q.min_confidence,
            sku_filter=q.sku_filter,
            page=q.page,
            page_size=q.page_size,
            sort_by=q.sort_by,
            sort_dir=q.sort_dir,
            job_id=repo_job_id,
        )

    def list_by_aisles(self, aisle_ids: Sequence[str]) -> Sequence[Position]:
        want = set(aisle_ids)
        return [p for p in self._positions if p.aisle_id in want]


class StubSourceAssetRepo(SourceAssetRepository):
    """Returns canned rollups for requested aisle ids (empty when unknown)."""

    def __init__(self, rollup_by_aisle: dict[str, AisleAssetRollup] | None = None) -> None:
        self._rollup = rollup_by_aisle or {}

    def save(self, asset: SourceAsset) -> None:
        pass

    def get_by_id(self, asset_id: str) -> SourceAsset | None:
        return None

    def delete_by_id(self, asset_id: str) -> bool:
        return False

    def list_by_aisle(self, aisle_id: str) -> Sequence[SourceAsset]:
        return []

    def get_by_capture_session_item_id(self, capture_session_item_id: str) -> SourceAsset | None:
        return None

    def get_by_upload_idempotency_key(
        self, aisle_id: str, upload_batch_id: str, upload_client_file_id: str
    ) -> SourceAsset | None:
        return None

    def summarize_assets_for_aisles(self, aisle_ids: Sequence[str]) -> dict[str, AisleAssetRollup]:
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
        result_context_resolver=ResultContextResolver(job_repo, StubPositionRepo([])),
    )
    result, total = use_case.execute("inv-1")

    assert total == 2
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
        result_context_resolver=ResultContextResolver(job_repo, pos_repo),
    )
    result, total = use_case.execute("inv-1")
    assert total == 1
    assert len(result) == 1
    row = result[0]
    assert row.assets_count == 3
    assert row.positions_count == 2
    assert row.pending_review_positions_count == 1
    assert row.last_activity_at == max(now, later, later, later)


def test_list_aisles_with_status_last_activity_at_can_win_on_latest_job_only() -> None:
    """When aisle, positions, and asset rollup are older than the latest job, max must follow the job."""
    t_old = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t_job = datetime(2025, 6, 15, 9, 30, 0, tzinfo=timezone.utc)
    a1 = Aisle("a1", "inv-1", "A-01", AisleStatus.PROCESSED, t_old, t_old)
    p1 = Position(
        "p1",
        "a1",
        PositionStatus.REVIEWED,
        0.95,
        False,
        None,
        t_old,
        t_old,
    )
    j1 = Job(
        "job-newest",
        "aisle",
        "a1",
        "process_aisle",
        JobStatus.SUCCEEDED,
        {},
        t_job,
        t_job,
    )
    inv_repo = StubInventoryRepo({"inv-1"})
    aisle_repo = StubAisleRepo([a1])
    job_repo = StubJobRepo({"a1": j1})
    pos_repo = StubPositionRepo([p1])
    src_repo = StubSourceAssetRepo({"a1": AisleAssetRollup(count=1, last_uploaded_at=t_old)})
    use_case = ListAislesWithStatusUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        position_repo=pos_repo,
        source_asset_repo=src_repo,
        result_context_resolver=ResultContextResolver(job_repo, pos_repo),
    )
    result, total = use_case.execute("inv-1")
    assert total == 1
    assert len(result) == 1
    assert result[0].last_activity_at == t_job


def test_list_aisles_positions_count_uses_operational_slice_not_all_runs() -> None:
    """Multi-run aisles: rollups count only the operational job slice (resolver semantics)."""
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    later = datetime(2025, 3, 7, 12, 0, 0, tzinfo=timezone.utc)
    a1 = Aisle("a1", "inv-1", "A-01", AisleStatus.PROCESSED, now, now, operational_job_id="job-2")
    j1 = Job("job-1", "aisle", "a1", "process_aisle", JobStatus.SUCCEEDED, {}, now, now)
    j2 = Job("job-2", "aisle", "a1", "process_aisle", JobStatus.SUCCEEDED, {}, later, later)
    job_repo = MemoryJobRepository()
    job_repo.save(j1)
    job_repo.save(j2)
    pos_repo = MemoryPositionRepository()
    for i in range(6):
        pos_repo.save(
            Position(
                f"p1-{i}",
                "a1",
                PositionStatus.DETECTED,
                0.9,
                True,
                None,
                now,
                now,
                job_id="job-1",
            )
        )
    for i in range(6):
        pos_repo.save(
            Position(
                f"p2-{i}",
                "a1",
                PositionStatus.DETECTED,
                0.9,
                True,
                None,
                later,
                later,
                job_id="job-2",
            )
        )
    inv_repo = StubInventoryRepo({"inv-1"})
    aisle_repo = StubAisleRepo([a1])
    use_case = ListAislesWithStatusUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        position_repo=pos_repo,
        source_asset_repo=StubSourceAssetRepo({}),
        result_context_resolver=ResultContextResolver(job_repo, pos_repo),
    )
    result, total = use_case.execute("inv-1")
    assert total == 1
    row = result[0]
    assert row.positions_count == 6
    assert row.pending_review_positions_count == 6
    assert row.latest_job is not None
    assert row.latest_job.id == "job-2"


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
        result_context_resolver=ResultContextResolver(job_repo, StubPositionRepo([])),
    )

    with pytest.raises(InventoryNotFoundError):
        use_case.execute("nonexistent")
