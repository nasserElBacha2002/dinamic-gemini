"""Unit tests for aisle processing-state resolver."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.application.services.aisle_processing_state import resolve_aisle_processing_state
from src.domain.jobs.entities import Job, JobStatus


def _job(
    *,
    job_id: str,
    status: JobStatus,
    created_offset_s: int = 0,
    idempotency_key: str | None = "key-1",
) -> Job:
    now = datetime.now(timezone.utc) - timedelta(seconds=created_offset_s)
    return Job(
        id=job_id,
        target_type="aisle",
        target_id="a1",
        job_type="process_aisle",
        status=status,
        payload_json={"idempotency_key": idempotency_key} if idempotency_key else {},
        created_at=now,
        updated_at=now,
        started_at=now,
    )


def test_idle_when_no_jobs():
    view = resolve_aisle_processing_state(
        latest_job=None, recent_jobs=(), operational_job_id=None
    )
    assert view.state == "IDLE"
    assert view.can_start_new is True


def test_running_blocks_new_start():
    job = _job(job_id="j1", status=JobStatus.RUNNING)
    view = resolve_aisle_processing_state(
        latest_job=job, recent_jobs=(job,), operational_job_id=job.id
    )
    assert view.state == "RUNNING"
    assert view.can_start_new is False
    assert view.job_id == "j1"


def test_stale_queued_requires_recovery():
    job = _job(job_id="j2", status=JobStatus.QUEUED, created_offset_s=10_000)
    view = resolve_aisle_processing_state(
        latest_job=job,
        recent_jobs=(job,),
        operational_job_id=None,
        stale_after_seconds=60,
    )
    assert view.state == "RECOVERY_REQUIRED"
    assert view.recoverable is True
    assert view.can_start_new is False
