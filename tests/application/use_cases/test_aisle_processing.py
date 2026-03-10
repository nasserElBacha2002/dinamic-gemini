"""Tests for StartAisleProcessingUseCase and GetAisleProcessingStatusUseCase."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence

import pytest

from src.application.ports.repositories import AisleRepository, JobRepository
from src.application.ports.services import JobQueue
from src.application.use_cases.get_aisle_processing_status import GetAisleProcessingStatusUseCase
from src.application.use_cases.start_aisle_processing import (
    ActiveJobExistsError,
    AisleNotFoundError,
    StartAisleProcessingCommand,
    StartAisleProcessingUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.jobs.entities import Job, JobStatus


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


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


class StubJobQueue(JobQueue):
    def __init__(self) -> None:
        self._ids: list[str] = []
        self._next_id = 0

    def enqueue(self, job_type: str, payload: Dict[str, Any]) -> str:
        job_id = f"job-{self._next_id}"
        self._next_id += 1
        self._ids.append(job_id)
        return job_id


def test_start_aisle_processing_creates_job_and_marks_aisle_queued() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.CREATED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    job_repo = StubJobRepo()
    queue = StubJobQueue()
    clock = FixedClock(now)

    use_case = StartAisleProcessingUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        job_queue=queue,
        clock=clock,
    )
    job_id = use_case.execute(StartAisleProcessingCommand(inventory_id="inv1", aisle_id="a1"))

    assert job_id == "job-0"
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


def test_start_aisle_processing_raises_when_aisle_not_found() -> None:
    aisle_repo = StubAisleRepo()
    job_repo = StubJobRepo()
    queue = StubJobQueue()
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)

    use_case = StartAisleProcessingUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        job_queue=queue,
        clock=FixedClock(now),
    )

    with pytest.raises(AisleNotFoundError):
        use_case.execute(StartAisleProcessingCommand(inventory_id="inv1", aisle_id="nonexistent"))


def test_start_aisle_processing_raises_when_aisle_belongs_to_other_inventory() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.CREATED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    job_repo = StubJobRepo()
    queue = StubJobQueue()

    use_case = StartAisleProcessingUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        job_queue=queue,
        clock=FixedClock(now),
    )

    with pytest.raises(AisleNotFoundError):
        use_case.execute(StartAisleProcessingCommand(inventory_id="other-inv", aisle_id="a1"))


def test_start_aisle_processing_raises_when_active_job_exists() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
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

    use_case = StartAisleProcessingUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        job_queue=queue,
        clock=FixedClock(now),
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
