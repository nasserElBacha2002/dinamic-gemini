from __future__ import annotations

import logging
from dataclasses import dataclass

from src.application.ports.artifact_publication_outbox_store import ArtifactPublicationOutboxStore
from src.application.ports.clock import Clock
from src.application.ports.repositories import AisleRepository, JobRepository
from src.domain.aisle.entities import AisleStatus
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

        logger.warning(
            "event=job_stale_detected job_id=%s aisle_id=%s owner=%s "
            "heartbeat_at=%s stale_threshold=%s",
            job.id,
            job.target_id if job.target_type == "aisle" else None,
            job.execution_id,
            reference,
            self.stale_after_seconds,
        )

        won = False
        used_cas = False
        try_fail = getattr(self.job_repo, "try_fail_stale_job", None)
        if callable(try_fail):
            try:
                won = bool(
                    try_fail(
                        job.id,
                        now=now,
                        stale_after_seconds=self.stale_after_seconds,
                    )
                )
                used_cas = True
            except NotImplementedError:
                used_cas = False

        if not used_cas:
            # Fallback for test doubles: mutate in memory then save (single-writer tests).
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
            won = True
        elif not won:
            # Another worker already reclaimed, or heartbeat refreshed — do not mutate aisle.
            return self.job_repo.get_by_id(job.id) or job

        refreshed = self.job_repo.get_by_id(job.id) or job
        self._reconcile_aisle_for_stale_job(refreshed, now=now)
        logger.warning(
            "event=job_stale_reclaimed job_id=%s aisle_id=%s previous_owner=%s "
            "new_status=failed attempt=%s",
            refreshed.id,
            refreshed.target_id if refreshed.target_type == "aisle" else None,
            refreshed.execution_id,
            refreshed.attempt_count,
        )
        return refreshed

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
        # Another active job for the same aisle → do not overwrite.
        list_fn = getattr(self.job_repo, "list_jobs_for_target", None)
        if callable(list_fn):
            others = [
                j
                for j in list_fn("aisle", job.target_id, limit=20)
                if j.id != job.id and j.status in STALE_RECONCILE_STATUSES
            ]
            if others:
                logger.warning(
                    "event=job_aisle_state_inconsistency job_id=%s aisle_id=%s "
                    "job_status=%s aisle_status=%s processing_job_id=%s",
                    job.id,
                    aisle.id,
                    job.status.value,
                    aisle.status.value,
                    others[0].id,
                )
                return
        aisle.mark_failed(
            now,
            error_code=STALE_FAILURE_CODE,
            error_message=STALE_FAILURE_MESSAGE,
            retryable=True,
        )
        self.aisle_repo.save(aisle)
