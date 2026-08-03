"""Unit tests for aisle processing-state resolver."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.application.services.aisle_processing_state import resolve_aisle_processing_state
from src.domain.jobs.entities import Job, JobStatus


class _FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def _job(
    *,
    job_id: str,
    status: JobStatus,
    created_offset_s: int = 0,
    idempotency_key: str | None = "key-1",
    claim_owner_id: str | None = None,
    lease_expires_at: datetime | None = None,
    last_heartbeat_at: datetime | None = None,
    failure_code: str | None = None,
    now: datetime | None = None,
) -> Job:
    base = now or datetime.now(timezone.utc)
    created = base - timedelta(seconds=created_offset_s)
    return Job(
        id=job_id,
        target_type="aisle",
        target_id="a1",
        job_type="process_aisle",
        status=status,
        payload_json={"idempotency_key": idempotency_key} if idempotency_key else {},
        created_at=created,
        updated_at=created,
        started_at=created,
        claim_owner_id=claim_owner_id,
        lease_expires_at=lease_expires_at,
        last_heartbeat_at=last_heartbeat_at,
        failure_code=failure_code,
    )


def test_idle_when_no_jobs():
    view = resolve_aisle_processing_state(
        latest_job=None, recent_jobs=(), operational_job_id=None
    )
    assert view.state == "IDLE"
    assert view.can_start_new is True


def test_running_blocks_new_start():
    now = datetime.now(timezone.utc)
    job = _job(
        job_id="j1",
        status=JobStatus.RUNNING,
        claim_owner_id="worker-1",
        lease_expires_at=now + timedelta(minutes=5),
        last_heartbeat_at=now,
        now=now,
    )
    view = resolve_aisle_processing_state(
        latest_job=job,
        recent_jobs=(job,),
        operational_job_id=job.id,
        clock=_FixedClock(now),
    )
    assert view.state == "RUNNING"
    assert view.can_start_new is False
    assert view.job_id == "j1"


def test_stale_queued_without_lease_requires_recovery():
    now = datetime.now(timezone.utc)
    job = _job(job_id="j2", status=JobStatus.QUEUED, created_offset_s=10_000, now=now)
    view = resolve_aisle_processing_state(
        latest_job=job,
        recent_jobs=(job,),
        operational_job_id=None,
        stale_after_seconds=60,
        clock=_FixedClock(now),
    )
    assert view.state == "RECOVERY_REQUIRED"
    assert view.recoverable is True
    assert view.can_start_new is False


def test_running_with_live_lease_not_recovery_even_if_old():
    now = datetime.now(timezone.utc)
    job = _job(
        job_id="j3",
        status=JobStatus.RUNNING,
        created_offset_s=10_000,
        claim_owner_id="worker-1",
        lease_expires_at=now + timedelta(minutes=2),
        last_heartbeat_at=now - timedelta(seconds=30),
        now=now,
    )
    view = resolve_aisle_processing_state(
        latest_job=job,
        recent_jobs=(job,),
        operational_job_id=job.id,
        stale_after_seconds=60,
        clock=_FixedClock(now),
    )
    assert view.state == "RUNNING"
    assert view.recoverable is False


def test_worker_launch_failed_is_recovery_required():
    now = datetime.now(timezone.utc)
    job = _job(
        job_id="j4",
        status=JobStatus.STARTING,
        failure_code="WORKER_LAUNCH_FAILED",
        now=now,
    )
    view = resolve_aisle_processing_state(
        latest_job=job,
        recent_jobs=(job,),
        operational_job_id=None,
        clock=_FixedClock(now),
    )
    assert view.state == "RECOVERY_REQUIRED"
    assert view.failure_code == "WORKER_LAUNCH_FAILED"
