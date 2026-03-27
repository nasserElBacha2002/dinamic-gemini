"""Tests for StartAisleProcessingUseCase and GetAisleProcessingStatusUseCase."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional, Sequence

import pytest

from src.application.ports.repositories import AisleRepository, InventoryRepository, JobRepository
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.ports.services import JobQueue
from src.application.use_cases.get_aisle_processing_status import GetAisleProcessingStatusUseCase
from src.application.use_cases.start_aisle_processing import (
    ActiveJobExistsError,
    AisleNotFoundError,
    StartAisleProcessingCommand,
    StartAisleProcessingUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus


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

    def get_by_id(self, inventory_id: str) -> Optional[Inventory]:
        return self._store.get(inventory_id)

    def list_all(self) -> Sequence[Inventory]:
        return list(self._store.values())


class StubAisleRepo(AisleRepository):
    def __init__(self) -> None:
        self._store: Dict[str, Aisle] = {}

    def save(self, aisle: Aisle) -> None:
        self._store[aisle.id] = aisle

    def get_by_id(self, aisle_id: str) -> Optional[Aisle]:
        return self._store.get(aisle_id)

    def list_by_inventory(self, inventory_id: str) -> Sequence[Aisle]:
        return [a for a in self._store.values() if a.inventory_id == inventory_id]

    def get_by_inventory_and_code(self, inventory_id: str, code: str) -> Optional[Aisle]:
        for a in self._store.values():
            if a.inventory_id == inventory_id and a.code == code.strip():
                return a
        return None


class StubJobRepo(JobRepository):
    def __init__(self) -> None:
        self._store: Dict[str, Job] = {}

    def save(self, job: Job) -> None:
        self._store[job.id] = job

    def get_by_id(self, job_id: str) -> Optional[Job]:
        return self._store.get(job_id)

    def get_latest_by_target(self, target_type: str, target_id: str) -> Optional[Job]:
        candidates = [
            j
            for j in self._store.values()
            if j.target_type == target_type and j.target_id == target_id
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda j: (j.updated_at, j.created_at), reverse=True)
        return candidates[0]

    def get_latest_by_targets(
        self, target_type: str, target_ids: Sequence[str]
    ) -> Dict[str, Job]:
        out: Dict[str, Job] = {}
        for tid in target_ids:
            latest = self.get_latest_by_target(target_type, tid)
            if latest is not None:
                out[tid] = latest
        return out


class StubJobQueue(JobQueue):
    def __init__(self) -> None:
        self.enqueued: list[str] = []

    def enqueue(self, job_id: str) -> None:
        self.enqueued.append(job_id)


def test_start_aisle_processing_creates_job_and_marks_aisle_queued() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo = StubInventoryRepo([Inventory("inv1", "W", InventoryStatus.DRAFT, now, now)])
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.CREATED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    job_repo = StubJobRepo()
    queue = StubJobQueue()
    clock = FixedClock(now)
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)

    use_case = StartAisleProcessingUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        job_queue=queue,
        clock=clock,
        status_reconciler=reconciler,
    )
    job_id = use_case.execute(StartAisleProcessingCommand(inventory_id="inv1", aisle_id="a1"))
    assert queue.enqueued == [job_id]
    saved_job = job_repo.get_by_id(job_id)
    assert saved_job is not None
    assert saved_job.target_type == "aisle"
    assert saved_job.target_id == "a1"
    assert saved_job.job_type == "process_aisle"
    assert saved_job.status == JobStatus.QUEUED
    assert saved_job.payload_json == {"aisle_id": "a1"}

    updated_aisle = aisle_repo.get_by_id("a1")
    assert updated_aisle is not None
    assert updated_aisle.status == AisleStatus.QUEUED
    assert inv_repo.get_by_id("inv1") is not None
    assert inv_repo.get_by_id("inv1").status == InventoryStatus.PROCESSING


def test_start_aisle_processing_persists_job_before_enqueue() -> None:
    """Regression test for the v3 queue race condition.

    The worker dequeues job ids from an in-memory queue. To avoid dequeuing a job
    before persistence, the use case must persist the job/aisle first, then enqueue.
    """
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo = StubInventoryRepo([Inventory("inv1", "W", InventoryStatus.DRAFT, now, now)])
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.CREATED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    job_repo = StubJobRepo()

    class AssertingJobQueue(JobQueue):
        def __init__(self) -> None:
            self.enqueued: list[str] = []

        def enqueue(self, job_id: str) -> None:
            # If enqueue is called before job persistence, this will fail.
            assert job_repo.get_by_id(job_id) is not None
            self.enqueued.append(job_id)

    queue = AssertingJobQueue()
    clock = FixedClock(now)
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)
    use_case = StartAisleProcessingUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        job_queue=queue,
        clock=clock,
        status_reconciler=reconciler,
    )

    job_id = use_case.execute(StartAisleProcessingCommand(inventory_id="inv1", aisle_id="a1"))
    assert queue.enqueued == [job_id]


def test_start_aisle_processing_marks_failed_when_enqueue_fails() -> None:
    """If enqueue(job_id) fails, do not leave QUEUED job/aisle behind."""
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo = StubInventoryRepo([Inventory("inv1", "W", InventoryStatus.DRAFT, now, now)])
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.CREATED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    job_repo = StubJobRepo()

    class FailingQueue(JobQueue):
        def __init__(self) -> None:
            self.captured_job_id: str | None = None

        def enqueue(self, job_id: str) -> None:
            self.captured_job_id = job_id
            raise RuntimeError("in-memory queue failure")

    queue = FailingQueue()
    clock = FixedClock(now)
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)
    use_case = StartAisleProcessingUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        job_queue=queue,
        clock=clock,
        status_reconciler=reconciler,
    )

    with pytest.raises(RuntimeError):
        use_case.execute(StartAisleProcessingCommand(inventory_id="inv1", aisle_id="a1"))

    assert queue.captured_job_id is not None
    saved_job = job_repo.get_by_id(queue.captured_job_id)
    assert saved_job is not None
    assert saved_job.status == JobStatus.FAILED
    assert saved_job.error_message is not None
    assert "in-memory queue failure" in saved_job.error_message

    updated_aisle = aisle_repo.get_by_id("a1")
    assert updated_aisle is not None
    assert updated_aisle.status == AisleStatus.FAILED
    assert updated_aisle.error_message is not None
    assert "in-memory queue failure" in updated_aisle.error_message
    assert inv_repo.get_by_id("inv1") is not None
    assert inv_repo.get_by_id("inv1").status == InventoryStatus.FAILED


def test_start_aisle_processing_raises_when_aisle_not_found() -> None:
    aisle_repo = StubAisleRepo()
    inv_repo = StubInventoryRepo([])
    job_repo = StubJobRepo()
    queue = StubJobQueue()
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock(now))

    use_case = StartAisleProcessingUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        job_queue=queue,
        clock=FixedClock(now),
        status_reconciler=reconciler,
    )

    with pytest.raises(AisleNotFoundError):
        use_case.execute(StartAisleProcessingCommand(inventory_id="inv1", aisle_id="nonexistent"))


def test_start_aisle_processing_raises_when_aisle_belongs_to_other_inventory() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.CREATED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    inv_repo = StubInventoryRepo([])
    job_repo = StubJobRepo()
    queue = StubJobQueue()
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock(now))

    use_case = StartAisleProcessingUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        job_queue=queue,
        clock=FixedClock(now),
        status_reconciler=reconciler,
    )

    with pytest.raises(AisleNotFoundError):
        use_case.execute(StartAisleProcessingCommand(inventory_id="other-inv", aisle_id="a1"))


def test_start_aisle_processing_raises_when_active_job_exists() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo = StubInventoryRepo([Inventory("inv1", "W", InventoryStatus.DRAFT, now, now)])
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.QUEUED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    job_repo = StubJobRepo()
    job_repo.save(
        Job(
            id="existing",
            target_type="aisle",
            target_id="a1",
            job_type="process_aisle",
            status=JobStatus.QUEUED,
            payload_json={},
            created_at=now,
            updated_at=now,
        )
    )
    queue = StubJobQueue()
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock(now))

    use_case = StartAisleProcessingUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        job_queue=queue,
        clock=FixedClock(now),
        status_reconciler=reconciler,
    )

    with pytest.raises(ActiveJobExistsError):
        use_case.execute(StartAisleProcessingCommand(inventory_id="inv1", aisle_id="a1"))


def test_get_aisle_processing_status_returns_aisle_and_latest_job() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.QUEUED, now, now)
    job = Job(
        id="j1",
        target_type="aisle",
        target_id="a1",
        job_type="process_aisle",
        status=JobStatus.QUEUED,
        payload_json={"aisle_id": "a1"},
        created_at=now,
        updated_at=now,
    )
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    job_repo = StubJobRepo()
    job_repo.save(job)

    use_case = GetAisleProcessingStatusUseCase(aisle_repo=aisle_repo, job_repo=job_repo)
    result = use_case.execute("inv1", "a1")

    assert result.aisle.id == "a1"
    assert result.aisle.status == AisleStatus.QUEUED
    assert result.latest_job is not None
    assert result.latest_job.id == "j1"
    assert result.latest_job.status == JobStatus.QUEUED


def test_get_aisle_processing_status_returns_none_job_when_no_job() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.CREATED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    job_repo = StubJobRepo()

    use_case = GetAisleProcessingStatusUseCase(aisle_repo=aisle_repo, job_repo=job_repo)
    result = use_case.execute("inv1", "a1")

    assert result.aisle.id == "a1"
    assert result.latest_job is None


def test_get_aisle_processing_status_raises_when_aisle_not_found() -> None:
    aisle_repo = StubAisleRepo()
    job_repo = StubJobRepo()
    use_case = GetAisleProcessingStatusUseCase(aisle_repo=aisle_repo, job_repo=job_repo)

    with pytest.raises(AisleNotFoundError):
        use_case.execute("inv1", "nonexistent")
