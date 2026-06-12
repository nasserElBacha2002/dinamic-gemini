from __future__ import annotations

import logging
from dataclasses import dataclass

from src.application.ports.clock import Clock
from src.application.ports.repositories import AisleRepository, JobRepository
from src.application.ports.artifact_publication_outbox_store import ArtifactPublicationOutboxStore
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.jobs.entities import Job, JobStatus
from src.domain.jobs.finalization import FinalizationStatus

logger = logging.getLogger(__name__)

STALE_RECONCILE_STATUSES = (
    JobStatus.STARTING,
    JobStatus.RUNNING,
    JobStatus.CANCEL_REQUESTED,
)
STALE_FAILURE_CODE = "STALE_JOB"
STALE_FAILURE_MESSAGE = "Job heartbeat expired before completion"

_AISLE_ACTIVE_STATUSES = frozenset(
    {
        AisleStatus.QUEUED,
        AisleStatus.PROCESSING,
    }
)


@dataclass
class JobStaleReconciler:
    """Single source of truth for stale active-job reconciliation."""

    job_repo: JobRepository
    clock: Clock
    stale_after_seconds: int
    aisle_repo: AisleRepository | None = None
    artifact_publication_outbox: ArtifactPublicationOutboxStore | None = None

    def reconcile(self, job: Job | None) -> Job | None:
        if job is None or self.stale_after_seconds <= 0:
            return job
        if job.status not in STALE_RECONCILE_STATUSES:
            return job
        if self.artifact_publication_outbox is not None:
            try:
                if self.artifact_publication_outbox.has_active_retryable_work(
                    job.id,
                    now=self.clock.now(),
                ):
                    return job
            except Exception:
                logger.warning(
                    "stale_reconcile.outbox_check_failed job_id=%s",
                    job.id,
                    exc_info=True,
                )
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

        if job.finalization_status in (
            FinalizationStatus.IN_PROGRESS,
            FinalizationStatus.NOT_STARTED,
        ):
            job.finalization_status = FinalizationStatus.FAILED
            if job.finalization_error_code is None:
                job.finalization_error_code = STALE_FAILURE_CODE
            if job.finalization_started_at is None:
                job.finalization_started_at = now

        self.job_repo.save(job)
        self._reconcile_aisle_for_stale_job(job, now=now)

        logger.warning(
            "stale_job_reconciled job_id=%s target_type=%s target_id=%s failure_code=%s",
            job.id,
            job.target_type,
            job.target_id,
            STALE_FAILURE_CODE,
        )
        return job

    def _reconcile_aisle_for_stale_job(self, job: Job, *, now) -> None:
        if self.aisle_repo is None:
            return
        if job.target_type != "aisle" or not job.target_id:
            return
        aisle = self.aisle_repo.get_by_id(job.target_id)
        if aisle is None:
            return
        if aisle.status not in _AISLE_ACTIVE_STATUSES:
            return
        aisle.mark_failed(
            now,
            error_code=STALE_FAILURE_CODE,
            error_message=STALE_FAILURE_MESSAGE,
            retryable=True,
        )
        self.aisle_repo.save(aisle)
