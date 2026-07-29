"""Persisted finalization progress updates for v3 worker jobs — Phase 3.2 (lease-fenced)."""

from __future__ import annotations

import json
import logging
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
from src.domain.jobs.finalization_evidence import EvidenceLevel
from src.domain.jobs.lease import JobLease, JobLeaseLostError, LeaseWriteOutcome
from src.infrastructure.pipeline.finalization_stage_recorder import FinalizationStageRecorder

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
    """Updates ``inventory_jobs`` finalization columns under an active :class:`JobLease`.

    All writes use ``update_finalization_if_leased`` / ``acknowledge_cancel_if_leased``.
    ``JobRepository.save(job)`` is never used for active-job finalization metadata.

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
        lease: JobLease,
        stage_recorder: FinalizationStageRecorder | None = None,
    ) -> None:
        if lease.job_id != job_id:
            raise ValueError(
                f"JobFinalizationTracker lease.job_id={lease.job_id!r} != job_id={job_id!r}"
            )
        self._job_repo = job_repo
        self._clock = clock
        self._job_id = job_id
        self._lease = lease
        self._stage_recorder = stage_recorder
        self._last_completed = LastCompletedFinalizationStep.NONE

    @property
    def job_id(self) -> str:
        return self._job_id

    @property
    def lease(self) -> JobLease:
        return self._lease

    @property
    def last_completed(self) -> LastCompletedFinalizationStep:
        return self._last_completed

    def assert_still_leased(self) -> None:
        """Raise :class:`JobLeaseLostError` if this tracker no longer holds the lease."""
        result = self._job_repo.assert_lease(self._lease, now=self._clock.now())
        if result.outcome == LeaseWriteOutcome.APPLIED:
            return
        raise JobLeaseLostError(
            "Lease lost during finalization side-effect gate",
            job_id=self._job_id,
            owner_id=self._lease.owner_id,
            fencing_token=self._lease.fencing_token,
            reason=result.reason,
        )

    def begin(self) -> None:
        now = self._clock.now()

        def _mutate(job: Job) -> None:
            job.finalization_status = FinalizationStatus.IN_PROGRESS
            job.finalization_started_at = now
            job.current_finalization_step = CurrentFinalizationStep.PERSIST_DOMAIN_RESULTS
            job.last_completed_finalization_step = LastCompletedFinalizationStep.NONE
            job.finalization_error_code = None
            job.finalization_error_metadata = None
            job.finalization_completed_at = None
            job.domain_persisted_at = None
            job.artifacts_published_at = None

        self._apply_leased(_mutate, operation="begin")
        self._last_completed = LastCompletedFinalizationStep.NONE
        if self._stage_recorder is not None:
            self._stage_recorder.mark_in_progress(
                self._job_id, CurrentFinalizationStep.PERSIST_DOMAIN_RESULTS
            )

    def set_current_step(self, step: CurrentFinalizationStep) -> None:
        def _mutate(job: Job) -> None:
            job.current_finalization_step = step

        self._apply_leased(_mutate, operation="set_current_step")

    def record_domain_persisted(self) -> None:
        """Mark domain snapshot committed (post-UoW — see class docstring)."""
        now = self._clock.now()

        def _mutate(job: Job) -> None:
            job.domain_persisted_at = now
            job.last_completed_finalization_step = LastCompletedFinalizationStep.DOMAIN_RESULTS_PERSISTED
            job.current_finalization_step = CurrentFinalizationStep.PUBLISH_ARTIFACTS

        self._apply_leased(_mutate, operation="record_domain_persisted")
        self._last_completed = LastCompletedFinalizationStep.DOMAIN_RESULTS_PERSISTED
        if self._stage_recorder is not None:
            self._stage_recorder.mark_completed_for_step(
                self._job_id,
                LastCompletedFinalizationStep.DOMAIN_RESULTS_PERSISTED,
                evidence_level=EvidenceLevel.POSITIVE_EVIDENCE_ONLY,
                verification_source="post_uow_marker",
            )

    def record_artifacts_published(
        self,
        *,
        durable_artifacts: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        now = self._clock.now()

        def _mutate(job: Job) -> None:
            job.artifacts_published_at = now
            job.last_completed_finalization_step = LastCompletedFinalizationStep.ARTIFACTS_PUBLISHED
            job.current_finalization_step = CurrentFinalizationStep.TERMINALIZE_JOB

        self._apply_leased(_mutate, operation="record_artifacts_published")
        self._last_completed = LastCompletedFinalizationStep.ARTIFACTS_PUBLISHED
        if self._stage_recorder is not None:
            if durable_artifacts:
                self._stage_recorder.record_artifact_manifest(self._job_id, durable_artifacts)
            self._stage_recorder.mark_completed_for_step(
                self._job_id,
                LastCompletedFinalizationStep.ARTIFACTS_PUBLISHED,
                evidence_level=EvidenceLevel.CONFIRMED,
                verification_source="artifact_upload",
            )

    def record_step_completed(self, step: LastCompletedFinalizationStep) -> None:
        def _mutate(job: Job) -> None:
            job.last_completed_finalization_step = step
            job.current_finalization_step = _next_current_after_completed(step)

        self._apply_leased(_mutate, operation="record_step_completed")
        self._last_completed = step
        if self._stage_recorder is not None:
            self._stage_recorder.mark_completed_for_step(
                self._job_id,
                step,
                evidence_level=EvidenceLevel.CONFIRMED,
            )

    def complete(self) -> None:
        now = self._clock.now()

        def _mutate(job: Job) -> None:
            job.finalization_status = FinalizationStatus.COMPLETED
            job.finalization_completed_at = now
            job.current_finalization_step = None
            job.last_completed_finalization_step = LastCompletedFinalizationStep.INVENTORY_RECONCILED
            job.finalization_error_code = None
            job.finalization_error_metadata = None

        self._apply_leased(_mutate, operation="complete")
        self._last_completed = LastCompletedFinalizationStep.INVENTORY_RECONCILED
        if self._stage_recorder is not None:
            self._stage_recorder.mark_completed_for_step(
                self._job_id,
                LastCompletedFinalizationStep.INVENTORY_RECONCILED,
                evidence_level=EvidenceLevel.CONFIRMED,
            )

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

        def _mutate(job: Job) -> None:
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

        self._apply_leased(_mutate, operation="fail")
        logger.error(
            "job_finalization_failed job_id=%s step=%s code=%s job_status=%s last_completed=%s",
            self._job_id,
            current_step.value,
            error_code.value,
            job_status.value,
            self._last_completed.value,
        )
        if self._stage_recorder is not None:
            self._stage_recorder.mark_failed_for_step(
                self._job_id,
                current_step,
                error_code=error_code.value,
                metadata=metadata,
            )

    def cancel_after_domain_commit(
        self,
        *,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Cancellation effective after domain UoW commit — results remain job-scoped."""
        now = self._clock.now()
        msg = reason[:2048] if len(reason) > 2048 else reason
        payload = dict(metadata or {})
        payload["cancel_after_domain_commit"] = True
        payload["reason"] = reason[:500]
        bounded = _bounded_metadata(payload)

        def _mutate(job: Job) -> None:
            job.status = JobStatus.CANCELED
            job.finished_at = now
            job.last_heartbeat_at = now
            job.finalization_status = FinalizationStatus.CANCELED
            job.current_finalization_step = CurrentFinalizationStep.PUBLISH_ARTIFACTS
            job.last_completed_finalization_step = LastCompletedFinalizationStep.DOMAIN_RESULTS_PERSISTED
            job.finalization_error_code = FinalizationErrorCode.FINALIZATION_CANCELED.value
            job.failure_code = FinalizationErrorCode.FINALIZATION_CANCELED.value
            job.failure_message = msg
            job.error_message = msg
            job.finalization_error_metadata = bounded

        self._apply_leased(_mutate, operation="cancel_after_domain_commit")

    def cancel_before_domain_commit(self, *, reason: str) -> None:
        now = self._clock.now()
        msg = reason[:2048] if len(reason) > 2048 else reason
        bounded = _bounded_metadata(
            {"cancel_before_domain_commit": True, "reason": reason[:500]}
        )

        def _mutate(job: Job) -> None:
            job.status = JobStatus.CANCELED
            job.finished_at = now
            job.last_heartbeat_at = now
            job.finalization_status = FinalizationStatus.CANCELED
            job.current_finalization_step = CurrentFinalizationStep.PERSIST_DOMAIN_RESULTS
            job.last_completed_finalization_step = LastCompletedFinalizationStep.NONE
            job.finalization_error_code = FinalizationErrorCode.FINALIZATION_CANCELED.value
            job.failure_code = FinalizationErrorCode.FINALIZATION_CANCELED.value
            job.failure_message = msg
            job.error_message = msg
            job.finalization_error_metadata = bounded

        self._apply_leased(_mutate, operation="cancel_before_domain_commit")

    def _apply_leased(self, mutator, *, operation: str) -> None:
        now = self._clock.now()
        result = self._job_repo.update_finalization_if_leased(
            self._lease, now=now, mutator=mutator
        )
        if result.outcome == LeaseWriteOutcome.APPLIED:
            return
        logger.info(
            "event=job_stale_write_rejected job_id=%s operation=finalization_%s "
            "owner_id=%s fencing_token=%s outcome=%s reason=%s",
            self._job_id,
            operation,
            self._lease.owner_id,
            self._lease.fencing_token,
            result.outcome.value,
            result.reason,
        )
        from src.application.services.job_lease_metrics import (
            METRIC_STALE_WRITE,
            inc_lease_metric,
        )

        inc_lease_metric(
            METRIC_STALE_WRITE, operation=f"finalization_{operation}", outcome=result.outcome.value
        )
        # LEASE_LOST: stop worker; do not register failure / mutate aisle / metadata further.
        raise JobLeaseLostError(
            f"Lease lost during finalization ({operation})",
            job_id=self._job_id,
            owner_id=self._lease.owner_id,
            fencing_token=self._lease.fencing_token,
            reason=result.reason,
        )


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
    except JobLeaseLostError:
        raise
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
    if isinstance(marker_exc, JobLeaseLostError):
        raise marker_exc
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
    except JobLeaseLostError:
        raise
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
