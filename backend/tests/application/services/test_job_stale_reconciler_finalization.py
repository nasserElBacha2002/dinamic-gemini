"""Job stale reconciler finalization + aisle reconciliation tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.application.services.job_stale_reconciler import JobStaleReconciler, STALE_FAILURE_CODE
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.jobs.entities import Job, JobStatus
from src.domain.jobs.finalization import FinalizationStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
from tests.support.worker_phase1.executor_harness import FixedClock


def _job(*, status: JobStatus, heartbeat_age_sec: int, finalization=FinalizationStatus.NOT_STARTED) -> Job:
    now = datetime(2026, 6, 12, 12, 0, 0, tzinfo=timezone.utc)
    return Job(
        id="job-1",
        target_type="aisle",
        target_id="aisle-1",
        job_type="aisle_processing",
        status=status,
        payload_json={},
        created_at=now - timedelta(hours=1),
        updated_at=now - timedelta(seconds=heartbeat_age_sec),
        last_heartbeat_at=now - timedelta(seconds=heartbeat_age_sec),
        finalization_status=finalization,
        finalization_started_at=now - timedelta(minutes=5) if finalization != FinalizationStatus.NOT_STARTED else None,
        current_finalization_step=None,
    )


def _aisle(*, status: AisleStatus = AisleStatus.PROCESSING) -> Aisle:
    now = datetime(2026, 6, 12, 12, 0, 0, tzinfo=timezone.utc)
    return Aisle(
        id="aisle-1",
        inventory_id="inv-1",
        code="A1",
        status=status,
        created_at=now,
        updated_at=now,
    )


def test_stale_running_before_finalization_marks_job_and_aisle_failed() -> None:
    job_repo = MemoryJobRepository()
    aisle_repo = MemoryAisleRepository()
    clock = FixedClock(datetime(2026, 6, 12, 12, 0, 0, tzinfo=timezone.utc))
    job = _job(status=JobStatus.RUNNING, heartbeat_age_sec=1200)
    aisle = _aisle()
    job_repo.save(job)
    aisle_repo.save(aisle)
    reconciler = JobStaleReconciler(job_repo=job_repo, aisle_repo=aisle_repo, clock=clock, stale_after_seconds=900)
    result = reconciler.reconcile(job)
    assert result is not None
    assert result.status == JobStatus.FAILED
    assert result.failure_code == STALE_FAILURE_CODE
    assert result.finalization_status == FinalizationStatus.FAILED
    saved_aisle = aisle_repo.get_by_id("aisle-1")
    assert saved_aisle is not None
    assert saved_aisle.status == AisleStatus.FAILED


def test_fresh_running_job_unchanged() -> None:
    job_repo = MemoryJobRepository()
    aisle_repo = MemoryAisleRepository()
    clock = FixedClock(datetime(2026, 6, 12, 12, 0, 0, tzinfo=timezone.utc))
    job = _job(status=JobStatus.RUNNING, heartbeat_age_sec=30)
    aisle = _aisle()
    job_repo.save(job)
    aisle_repo.save(aisle)
    reconciler = JobStaleReconciler(job_repo=job_repo, aisle_repo=aisle_repo, clock=clock, stale_after_seconds=900)
    result = reconciler.reconcile(job)
    assert result.status == JobStatus.RUNNING
    saved_aisle = aisle_repo.get_by_id("aisle-1")
    assert saved_aisle is not None
    assert saved_aisle.status == AisleStatus.PROCESSING
