from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.clock import Clock
from src.application.ports.repositories import JobRepository
from src.domain.jobs.entities import Job, JobStatus

STALE_RECONCILE_STATUSES = (
    JobStatus.STARTING,
    JobStatus.RUNNING,
    JobStatus.CANCEL_REQUESTED,
)
STALE_FAILURE_CODE = "STALE_JOB"
STALE_FAILURE_MESSAGE = "Job heartbeat expired before completion"


@dataclass
class JobStaleReconciler:
    """Single source of truth for stale active-job reconciliation."""

    job_repo: JobRepository
    clock: Clock
    stale_after_seconds: int

    def reconcile(self, job: Job | None) -> Job | None:
        if job is None or self.stale_after_seconds <= 0:
            return job
        if job.status not in STALE_RECONCILE_STATUSES:
            return job
        reference = job.last_heartbeat_at or job.updated_at
        now = self.clock.now()
        if (now - reference).total_seconds() < self.stale_after_seconds:
            return job
        job.status = JobStatus.FAILED
        job.failure_code = STALE_FAILURE_CODE
        job.failure_message = STALE_FAILURE_MESSAGE
        job.error_message = STALE_FAILURE_MESSAGE
        job.finished_at = now
        job.updated_at = now
        self.job_repo.save(job)
        return job
