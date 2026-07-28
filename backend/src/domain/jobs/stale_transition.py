"""Shared stale-failure transition applied identically by SQL and memory adapters."""

from __future__ import annotations

from datetime import datetime

from src.application.services.job_stale_reconciler import (
    STALE_FAILURE_CODE,
    STALE_FAILURE_MESSAGE,
)
from src.domain.jobs.entities import Job, JobStatus
from src.domain.jobs.finalization import FinalizationStatus


def apply_stale_failure_fields(job: Job, *, now: datetime) -> None:
    """Mutate ``job`` to the canonical STALE_JOB failed terminal state."""
    job.status = JobStatus.FAILED
    job.failure_code = STALE_FAILURE_CODE
    job.failure_message = STALE_FAILURE_MESSAGE
    job.error_message = STALE_FAILURE_MESSAGE
    job.finished_at = now
    job.updated_at = now
    if job.finalization_status in (
        FinalizationStatus.IN_PROGRESS,
        FinalizationStatus.NOT_STARTED,
    ):
        job.finalization_status = FinalizationStatus.FAILED
        if job.finalization_error_code is None:
            job.finalization_error_code = STALE_FAILURE_CODE
        if job.finalization_started_at is None:
            job.finalization_started_at = now
