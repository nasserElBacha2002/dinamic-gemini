"""Persisted finalization progress updates for v3 worker jobs — Phase 3.2."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from src.application.ports.clock import Clock
from src.application.ports.repositories import JobRepository
from src.domain.jobs.entities import Job, JobStatus
from src.domain.jobs.finalization import (
    CurrentFinalizationStep,
    FinalizationErrorCode,
    FinalizationStatus,
    LastCompletedFinalizationStep,
)

logger = logging.getLogger(__name__)

_METADATA_MAX = 4000

# Keys allowed in API-facing sanitized error metadata (diagnostic only).
_PUBLIC_ERROR_METADATA_KEYS = frozenset(
    {
        "domain_commit_completed",
        "artifact_upload_completed",
        "marker_write_completed",
        "verification_required",
        "failed_marker",
        "published_artifact_kinds",
        "exception_type",
        "promotion_outcome",
        "failed_kind",
        "published_artifacts",
        "cancel_after_domain_commit",
        "cancel_before_domain_commit",
        "reason",
    }
)


def _bounded_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        encoded = json.dumps(payload, ensure_ascii=False, default=str)
        if len(encoded) <= _METADATA_MAX:
            return payload
        return {"truncated": True, "preview": encoded[:_METADATA_MAX]}
    except (TypeError, ValueError):
        return {"serialization_error": True}


def sanitize_finalization_error_metadata(
    metadata: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return a client-safe subset of finalization error metadata."""
    if not metadata:
        return None
    sanitized = {
        key: metadata[key]
        for key in _PUBLIC_ERROR_METADATA_KEYS
        if key in metadata
    }
    return sanitized or None


class JobFinalizationTracker:
    """Updates ``inventory_jobs`` finalization columns for one execution attempt.

    ``DOMAIN_RESULTS_PERSISTED`` is written immediately after ``PersistAisleResultUseCase``
    commits (post-UoW). There is a small crash window between UoW commit and this marker;
    recovery must verify rows by ``job_id`` — absence of the marker is not proof of rollback.
    """

    def __init__(
        self,
        *,
        job_repo: JobRepository,
        clock: Clock,
        job_id: str,
    ) -> None:
        self._job_repo = job_repo
        self._clock = clock
        self._job_id = job_id
        self._last_completed = LastCompletedFinalizationStep.NONE

    @property
    def job_id(self) -> str:
        return self._job_id

    @property
    def last_completed(self) -> LastCompletedFinalizationStep:
        return self._last_completed

    def begin(self) -> None:
        now = self._clock.now()
        job = self._require_job()
        job.finalization_status = FinalizationStatus.IN_PROGRESS
        job.finalization_started_at = now
        job.current_finalization_step = CurrentFinalizationStep.PERSIST_DOMAIN_RESULTS
        job.last_completed_finalization_step = LastCompletedFinalizationStep.NONE
        job.finalization_error_code = None
        job.finalization_error_metadata = None
        job.finalization_completed_at = None
        job.domain_persisted_at = None
        job.artifacts_published_at = None
        job.updated_at = now
        self._job_repo.save(job)
        self._last_completed = LastCompletedFinalizationStep.NONE

    def set_current_step(self, step: CurrentFinalizationStep) -> None:
        now = self._clock.now()
        job = self._require_job()
        job.current_finalization_step = step
        job.updated_at = now
        self._job_repo.save(job)

    def record_domain_persisted(self) -> None:
        """Mark domain snapshot committed (post-UoW — see class docstring)."""
        now = self._clock.now()
        job = self._require_job()
        job.domain_persisted_at = now
        job.last_completed_finalization_step = LastCompletedFinalizationStep.DOMAIN_RESULTS_PERSISTED
        job.current_finalization_step = CurrentFinalizationStep.PUBLISH_ARTIFACTS
        job.updated_at = now
        self._job_repo.save(job)
        self._last_completed = LastCompletedFinalizationStep.DOMAIN_RESULTS_PERSISTED

    def record_artifacts_published(
        self,
        *,
        durable_artifacts: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        now = self._clock.now()
        job = self._require_job()
        job.artifacts_published_at = now
        job.last_completed_finalization_step = LastCompletedFinalizationStep.ARTIFACTS_PUBLISHED
        job.current_finalization_step = CurrentFinalizationStep.TERMINALIZE_JOB
        job.updated_at = now
        self._job_repo.save(job)
        self._last_completed = LastCompletedFinalizationStep.ARTIFACTS_PUBLISHED

    def record_step_completed(self, step: LastCompletedFinalizationStep) -> None:
        now = self._clock.now()
        job = self._require_job()
        job.last_completed_finalization_step = step
        job.updated_at = now
        next_step = _next_current_after_completed(step)
        job.current_finalization_step = next_step
        self._job_repo.save(job)
        self._last_completed = step

    def complete(self) -> None:
        now = self._clock.now()
        job = self._require_job()
        job.finalization_status = FinalizationStatus.COMPLETED
        job.finalization_completed_at = now
        job.current_finalization_step = None
        job.last_completed_finalization_step = LastCompletedFinalizationStep.INVENTORY_RECONCILED
        job.finalization_error_code = None
        job.finalization_error_metadata = None
        job.updated_at = now
        self._job_repo.save(job)
        self._last_completed = LastCompletedFinalizationStep.INVENTORY_RECONCILED

    def fail(
        self,
        *,
        error_code: FinalizationErrorCode,
        current_step: CurrentFinalizationStep,
        message: str,
        metadata: dict[str, Any] | None = None,
        job_status: JobStatus = JobStatus.FAILED,
    ) -> None:
        now = self._clock.now()
        job = self._require_job()
        if job_status == JobStatus.FAILED:
            job.status = JobStatus.FAILED
            job.finished_at = now
            job.last_heartbeat_at = now
        elif job_status == JobStatus.SUCCEEDED:
            job.status = JobStatus.SUCCEEDED
            job.last_heartbeat_at = now
        job.finalization_status = FinalizationStatus.FAILED
        job.current_finalization_step = current_step
        job.finalization_error_code = error_code.value
        job.failure_code = error_code.value
        job.failure_message = message[:2048] if len(message) > 2048 else message
        job.error_message = job.failure_message
        payload = dict(metadata or {})
        payload["failure_message"] = message[:500]
        job.finalization_error_metadata = _bounded_metadata(payload)
        job.updated_at = now
        self._job_repo.save(job)
        logger.error(
            "job_finalization_failed job_id=%s step=%s code=%s job_status=%s last_completed=%s",
            self._job_id,
            current_step.value,
            error_code.value,
            job.status.value,
            job.last_completed_finalization_step.value,
        )

    def cancel_after_domain_commit(
        self,
        *,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Cancellation effective after domain UoW commit — results remain job-scoped."""
        now = self._clock.now()
        job = self._require_job()
        job.status = JobStatus.CANCELED
        job.finished_at = now
        job.last_heartbeat_at = now
        job.finalization_status = FinalizationStatus.CANCELED
        job.current_finalization_step = CurrentFinalizationStep.PUBLISH_ARTIFACTS
        job.last_completed_finalization_step = LastCompletedFinalizationStep.DOMAIN_RESULTS_PERSISTED
        job.finalization_error_code = FinalizationErrorCode.FINALIZATION_CANCELED.value
        job.failure_code = FinalizationErrorCode.FINALIZATION_CANCELED.value
        job.failure_message = reason[:2048] if len(reason) > 2048 else reason
        job.error_message = job.failure_message
        payload = dict(metadata or {})
        payload["cancel_after_domain_commit"] = True
        payload["reason"] = reason[:500]
        job.finalization_error_metadata = _bounded_metadata(payload)
        job.updated_at = now
        self._job_repo.save(job)

    def cancel_before_domain_commit(self, *, reason: str) -> None:
        now = self._clock.now()
        job = self._require_job()
        job.status = JobStatus.CANCELED
        job.finished_at = now
        job.last_heartbeat_at = now
        job.finalization_status = FinalizationStatus.CANCELED
        job.current_finalization_step = CurrentFinalizationStep.PERSIST_DOMAIN_RESULTS
        job.last_completed_finalization_step = LastCompletedFinalizationStep.NONE
        job.finalization_error_code = FinalizationErrorCode.FINALIZATION_CANCELED.value
        job.failure_code = FinalizationErrorCode.FINALIZATION_CANCELED.value
        job.failure_message = reason[:2048] if len(reason) > 2048 else reason
        job.error_message = job.failure_message
        job.finalization_error_metadata = _bounded_metadata(
            {"cancel_before_domain_commit": True, "reason": reason[:500]}
        )
        job.updated_at = now
        self._job_repo.save(job)

    def _require_job(self) -> Job:
        job = self._job_repo.get_by_id(self._job_id)
        if job is None:
            raise RuntimeError(f"Job not found for finalization tracking: {self._job_id}")
        return job


def report_finalization_failure(
    tracker: JobFinalizationTracker,
    *,
    error_code: FinalizationErrorCode,
    current_step: CurrentFinalizationStep,
    message: str,
    metadata: dict[str, Any] | None = None,
    job_status: JobStatus = JobStatus.FAILED,
) -> None:
    """Persist finalization failure metadata; critical-log if the job repo is unavailable."""
    try:
        tracker.fail(
            error_code=error_code,
            current_step=current_step,
            message=message,
            metadata=metadata,
            job_status=job_status,
        )
    except Exception as reporting_exc:
        logger.critical(
            "finalization_failure_reporting_failed",
            extra={
                "job_id": tracker.job_id,
                "original_error_code": error_code.value,
                "original_step": current_step.value,
                "known_last_completed_step": tracker.last_completed.value,
                "intended_job_status": job_status.value,
                "reporting_error_type": type(reporting_exc).__name__,
                "reporting_error": str(reporting_exc)[:500],
            },
        )
        raise reporting_exc


def report_metadata_marker_failure(
    tracker: JobFinalizationTracker,
    *,
    failed_marker: str,
    current_step: CurrentFinalizationStep,
    marker_exc: Exception,
    diagnostic_metadata: dict[str, Any],
    job_status: JobStatus = JobStatus.FAILED,
) -> None:
    """Report post-operation marker persistence failure without misclassifying the upstream step."""
    metadata = {
        "marker_write_completed": False,
        "verification_required": True,
        "failed_marker": failed_marker,
        **diagnostic_metadata,
    }
    message = f"Finalization marker write failed ({failed_marker}): {marker_exc}"
    try:
        tracker.fail(
            error_code=FinalizationErrorCode.FINALIZATION_METADATA_WRITE_FAILED,
            current_step=current_step,
            message=message,
            metadata=metadata,
            job_status=job_status,
        )
    except Exception as reporting_exc:
        logger.critical(
            "finalization_metadata_write_failure_reporting_failed",
            extra={
                "job_id": tracker.job_id,
                "failed_marker": failed_marker,
                "known_completed_operation": diagnostic_metadata,
                "marker_error_type": type(marker_exc).__name__,
                "marker_error": str(marker_exc)[:500],
                "reporting_error_type": type(reporting_exc).__name__,
                "reporting_error": str(reporting_exc)[:500],
                "verification_required": True,
            },
        )
        raise marker_exc from reporting_exc


def _next_current_after_completed(
    completed: LastCompletedFinalizationStep,
) -> CurrentFinalizationStep | None:
    mapping: dict[LastCompletedFinalizationStep, CurrentFinalizationStep | None] = {
        LastCompletedFinalizationStep.JOB_TERMINALIZED: (
            CurrentFinalizationStep.PROMOTE_OPERATIONAL_RESULT
        ),
        LastCompletedFinalizationStep.OPERATIONAL_RESULT_PROMOTED: (
            CurrentFinalizationStep.UPDATE_AISLE
        ),
        LastCompletedFinalizationStep.AISLE_UPDATED: CurrentFinalizationStep.RECONCILE_INVENTORY,
        LastCompletedFinalizationStep.INVENTORY_RECONCILED: None,
    }
    return mapping.get(completed)
