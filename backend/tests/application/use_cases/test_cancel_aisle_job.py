"""Tests for CancelAisleJobUseCase — v3.2.5 Phase 3 Block 1 (cancel-state contract)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional, Sequence

import pytest

from src.application.use_cases.cancel_aisle_job import CancelAisleJobCommand, CancelAisleJobUseCase
from src.application.errors import AisleNotFoundError
from src.application.ports.clock import Clock
from src.application.ports.repositories import AisleRepository, JobRepository
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.jobs.entities import Job, JobStatus


class FixedClock(Clock):
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class InMemoryAisleRepo(AisleRepository):
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


class InMemoryJobRepo(JobRepository):
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
        result = {}
        for tid in target_ids:
            j = self.get_latest_by_target(target_type, tid)
            if j is not None:
                result[tid] = j
        return result

    def list_jobs_for_target(
        self, target_type: str, target_id: str, *, limit: int = 50
    ) -> Sequence[Job]:
        candidates = [
            j
            for j in self._store.values()
            if j.target_type == target_type and j.target_id == target_id
        ]
        candidates.sort(key=lambda j: (j.updated_at, j.created_at), reverse=True)
        n = max(1, int(limit))
        return candidates[:n]


def test_cancel_queued_job_marks_canceled() -> None:
    """Phase 3 Block 1 Case 1: QUEUED -> CANCELED; job is persisted."""
    now = datetime(2025, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
    aisle = Aisle("aisle-1", "inv-1", "R01", AisleStatus.CREATED, now, now)
    job = Job(
        id="job-1",
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.QUEUED,
        payload_json={"aisle_id": "aisle-1"},
        created_at=now,
        updated_at=now,
    )
    aisle_repo = InMemoryAisleRepo([aisle])
    job_repo = InMemoryJobRepo()
    job_repo.save(job)
    clock = FixedClock(now)

    use_case = CancelAisleJobUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        clock=clock,
    )
    use_case.execute(
        CancelAisleJobCommand(inventory_id="inv-1", aisle_id="aisle-1", job_id="job-1")
    )

    updated = job_repo.get_by_id("job-1")
    assert updated is not None
    assert updated.status == JobStatus.CANCELED
    assert "canceled" in (updated.error_message or "").lower()
    assert updated.cancel_requested_at is None
    assert updated.finished_at == now


def test_cancel_running_job_marks_cancel_requested() -> None:
    """Phase 3 Block 1 Case 2: RUNNING -> CANCEL_REQUESTED; persisted."""
    now = datetime(2025, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
    aisle = Aisle("aisle-1", "inv-1", "R01", AisleStatus.CREATED, now, now)
    job = Job(
        id="job-1",
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.RUNNING,
        payload_json={"aisle_id": "aisle-1"},
        created_at=now,
        updated_at=now,
    )
    aisle_repo = InMemoryAisleRepo([aisle])
    job_repo = InMemoryJobRepo()
    job_repo.save(job)
    clock = FixedClock(now)

    use_case = CancelAisleJobUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        clock=clock,
    )
    use_case.execute(
        CancelAisleJobCommand(inventory_id="inv-1", aisle_id="aisle-1", job_id="job-1")
    )

    updated = job_repo.get_by_id("job-1")
    assert updated is not None
    assert updated.status == JobStatus.CANCEL_REQUESTED
    assert updated.cancel_requested_at == now


def test_cancel_starting_job_marks_cancel_requested() -> None:
    now = datetime(2025, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
    aisle = Aisle("aisle-1", "inv-1", "R01", AisleStatus.CREATED, now, now)
    job = Job(
        id="job-1",
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.STARTING,
        payload_json={"aisle_id": "aisle-1"},
        created_at=now,
        updated_at=now,
    )
    aisle_repo = InMemoryAisleRepo([aisle])
    job_repo = InMemoryJobRepo()
    job_repo.save(job)
    clock = FixedClock(now)

    use_case = CancelAisleJobUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        clock=clock,
    )
    returned = use_case.execute(
        CancelAisleJobCommand(inventory_id="inv-1", aisle_id="aisle-1", job_id="job-1")
    )

    updated = job_repo.get_by_id("job-1")
    assert updated is not None
    assert returned is updated
    assert updated.status == JobStatus.CANCEL_REQUESTED
    assert updated.cancel_requested_at == now


def test_cancel_terminal_job_raises() -> None:
    """Phase 3 Block 1 Case 3: SUCCEEDED/FAILED/CANCELED/TIMED_OUT reject cancellation."""
    now = datetime(2025, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
    aisle = Aisle("aisle-1", "inv-1", "R01", AisleStatus.CREATED, now, now)
    aisle_repo = InMemoryAisleRepo([aisle])
    clock = FixedClock(now)

    for terminal in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELED, JobStatus.TIMED_OUT):
        job_repo = InMemoryJobRepo()
        job = Job(
            id="job-1",
            target_type="aisle",
            target_id="aisle-1",
            job_type="process_aisle",
            status=terminal,
            payload_json={"aisle_id": "aisle-1"},
            created_at=now,
            updated_at=now,
        )
        job_repo.save(job)
        use_case = CancelAisleJobUseCase(
            aisle_repo=aisle_repo,
            job_repo=job_repo,
            clock=clock,
        )
        with pytest.raises(ValueError, match="terminal state"):
            use_case.execute(
                CancelAisleJobCommand(
                    inventory_id="inv-1", aisle_id="aisle-1", job_id="job-1"
                )
            )
        assert job_repo.get_by_id("job-1").status == terminal


def test_cancel_cancel_requested_idempotent() -> None:
    """CANCEL_REQUESTED -> CANCEL_REQUESTED (idempotent); no error."""
    now = datetime(2025, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
    aisle = Aisle("aisle-1", "inv-1", "R01", AisleStatus.CREATED, now, now)
    job = Job(
        id="job-1",
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.CANCEL_REQUESTED,
        payload_json={"aisle_id": "aisle-1"},
        created_at=now,
        updated_at=now,
    )
    aisle_repo = InMemoryAisleRepo([aisle])
    job_repo = InMemoryJobRepo()
    job_repo.save(job)
    clock = FixedClock(now)

    use_case = CancelAisleJobUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        clock=clock,
    )
    use_case.execute(
        CancelAisleJobCommand(inventory_id="inv-1", aisle_id="aisle-1", job_id="job-1")
    )

    updated = job_repo.get_by_id("job-1")
    assert updated is not None
    assert updated.status == JobStatus.CANCEL_REQUESTED


def test_cancel_non_process_aisle_job_raises_value_error_with_stable_message() -> None:
    now = datetime(2025, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
    aisle = Aisle("aisle-1", "inv-1", "R01", AisleStatus.CREATED, now, now)
    job = Job(
        id="job-1",
        target_type="aisle",
        target_id="aisle-1",
        job_type="export_inventory",
        status=JobStatus.QUEUED,
        payload_json={},
        created_at=now,
        updated_at=now,
    )
    aisle_repo = InMemoryAisleRepo([aisle])
    job_repo = InMemoryJobRepo()
    job_repo.save(job)
    clock = FixedClock(now)
    use_case = CancelAisleJobUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        clock=clock,
    )
    with pytest.raises(
        ValueError,
        match=r"^Job job-1 is not a process_aisle job$",
    ):
        use_case.execute(
            CancelAisleJobCommand(inventory_id="inv-1", aisle_id="aisle-1", job_id="job-1")
        )


def test_cancel_when_job_missing_raises_aisle_not_found() -> None:
    """When the job is not in the repo, use case raises AisleNotFoundError so the API can return 404 (job/aisle not found)."""
    now = datetime(2025, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
    aisle = Aisle("aisle-1", "inv-1", "R01", AisleStatus.CREATED, now, now)
    aisle_repo = InMemoryAisleRepo([aisle])
    job_repo = InMemoryJobRepo()
    clock = FixedClock(now)

    use_case = CancelAisleJobUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        clock=clock,
    )
    with pytest.raises(
        AisleNotFoundError,
        match=r"^Job nonexistent not found for aisle aisle-1$",
    ):
        use_case.execute(
            CancelAisleJobCommand(
                inventory_id="inv-1", aisle_id="aisle-1", job_id="nonexistent"
            )
        )
