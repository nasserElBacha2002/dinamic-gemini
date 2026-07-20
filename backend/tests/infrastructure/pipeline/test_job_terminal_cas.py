"""CAS terminal transitions for v3 job execution state."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Thread
from unittest.mock import MagicMock

from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.aisle_identification.modes import AisleIdentificationExecutionStrategy
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.pipeline.v3_job_execution_state import V3JobExecutionStateService
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository


class _Clock:
    def now(self):
        return datetime(2026, 7, 20, 12, 0, 0, tzinfo=timezone.utc)


def _job(status: JobStatus) -> Job:
    now = _Clock().now()
    return Job(
        id="job-1",
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=status,
        payload_json={},
        created_at=now,
        updated_at=now,
        execution_strategy=AisleIdentificationExecutionStrategy.CODE_SCAN,
    )


def _aisle() -> Aisle:
    now = _Clock().now()
    return Aisle(
        id="aisle-1",
        inventory_id="inv-1",
        code="A01",
        status=AisleStatus.PROCESSING,
        created_at=now,
        updated_at=now,
    )


def _state():
    jobs = MemoryJobRepository()
    aisles = MemoryAisleRepository()
    jobs.save(_job(JobStatus.RUNNING))
    aisles.save(_aisle())
    state = V3JobExecutionStateService(
        job_repo=jobs,
        aisle_repo=aisles,
        inventory_repo=MagicMock(),
        clock=_Clock(),
        inventory_status_reconciler=MagicMock(spec=InventoryStatusReconciler),
    )
    return state, jobs


def test_try_transition_to_failed_wins_once() -> None:
    state, jobs = _state()
    assert state.try_transition_to_failed("job-1", "boom", failure_code="X") is True
    assert state.try_transition_to_failed("job-1", "again", failure_code="Y") is False
    stored = jobs.get_by_id("job-1")
    assert stored is not None
    assert stored.status is JobStatus.FAILED
    assert stored.failure_code == "X"


def test_failed_job_cannot_finalize_success() -> None:
    state, jobs = _state()
    jobs.save(_job(JobStatus.FAILED))
    assert state.try_transition_to_succeeded("job-1") is None


def test_concurrent_fail_only_one_wins() -> None:
    state, _jobs = _state()
    results: list[bool] = []

    def _race(code: str) -> None:
        results.append(state.try_transition_to_failed("job-1", "race", failure_code=code))

    t1 = Thread(target=_race, args=("A",))
    t2 = Thread(target=_race, args=("B",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert results.count(True) == 1
    assert results.count(False) == 1
