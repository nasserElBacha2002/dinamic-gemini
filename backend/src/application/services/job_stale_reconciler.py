from __future__ import annotations

import logging
from dataclasses import dataclass

from src.application.ports.artifact_publication_outbox_store import ArtifactPublicationOutboxStore
from src.application.ports.clock import Clock
from src.application.ports.repositories import AisleRepository, JobRepository
from src.domain.aisle.entities import AisleStatus
from src.domain.jobs.entities import Job, JobStatus

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

        logger.warning(
            "event=job_stale_detected job_id=%s aisle_id=%s owner=%s "
            "heartbeat_at=%s stale_threshold=%s",
            job.id,
            job.target_id if job.target_type == "aisle" else None,
            job.claim_owner_id or job.execution_id,
            reference,
            self.stale_after_seconds,
        )

        result = self.job_repo.try_reclaim_stale_job_and_reconcile_aisle(
            job.id,
            now=now,
            stale_after_seconds=self.stale_after_seconds,
        )
        if not result.won:
            return self.job_repo.get_by_id(job.id) or job

        try:
            from src.observability.metrics.instruments import record_job_outcome

            record_job_outcome(job_type=getattr(job, "job_type", None) or "aisle", outcome="stale")
        except Exception:
            logger.warning("event=job_stale_metric_failed job_id=%s", job.id, exc_info=True)
        refreshed = result.job or self.job_repo.get_by_id(job.id) or job
        logger.warning(
            "event=job_stale_reclaimed job_id=%s aisle_id=%s previous_owner=%s "
            "new_status=failed attempt=%s aisle_transition_applied=%s",
            refreshed.id,
            refreshed.target_id if refreshed.target_type == "aisle" else None,
            refreshed.claim_owner_id or refreshed.execution_id,
            refreshed.attempt_count,
            result.aisle_transition_applied,
        )
        return refreshed
