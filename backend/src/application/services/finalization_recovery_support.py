"""Shared helpers for manual finalization recovery — Phase 3.4."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from src.application.ports.clock import Clock
from src.application.ports.finalization_recovery_store import (
    FinalizationRecoveryStore,
    RecoveryLeaseConflictError,
)
from src.application.ports.repositories import JobRepository
from src.application.ports.finalization_stage_store import FinalizationStageStore
from src.application.ports.repositories import JobRepository
from src.application.services.finalization_assessment_service import FinalizationAssessmentService
from src.application.services.finalization_projection_service import FinalizationProjectionService
from src.application.services.finalization_recovery_eligibility import FinalizationRecoveryEligibility
from src.domain.jobs.finalization_evidence import FinalizationAssessment
from src.domain.jobs.finalization_recovery import (
    RecoveryAttemptStatus,
    RecoveryOutcome,
    RecoveryResult,
)
from src.infrastructure.pipeline.finalization_stage_recorder import FinalizationStageRecorder

DEFAULT_RECOVERY_LEASE_SECONDS = 300


def sanitize_recovery_message(message: str | None) -> str | None:
    if not message:
        return None
    text = message.strip()
    if not text:
        return None
    if len(text) > 500:
        return text[:500]
    lowered = text.lower()
    for token in ("password", "secret", "traceback", "aws_", "credential"):
        if token in lowered:
            return "recovery_failed"
    return text


def build_stage_recorder(
    *,
    job_repo: JobRepository,
    stage_store: FinalizationStageStore,
    manifest_store,
    clock: Clock,
) -> FinalizationStageRecorder:
    projection = FinalizationProjectionService(
        job_repo=job_repo,
        stage_store=stage_store,
        clock=clock,
    )
    return FinalizationStageRecorder(
        stage_store=stage_store,
        projection=projection,
        manifest_store=manifest_store,
        clock=clock,
    )


class RecoverySession:
    """Lease + audit wrapper for a single recovery command."""

    def __init__(
        self,
        *,
        recovery_store: FinalizationRecoveryStore,
        assessment_service: FinalizationAssessmentService,
        eligibility: FinalizationRecoveryEligibility,
        job_repo: JobRepository,
        clock: Clock,
        lease_seconds: int = DEFAULT_RECOVERY_LEASE_SECONDS,
    ) -> None:
        self._recovery_store = recovery_store
        self._assessment_service = assessment_service
        self._eligibility = eligibility
        self._job_repo = job_repo
        self._clock = clock
        self._lease_seconds = lease_seconds
        self._attempt_id: str | None = None
        self._recovery_id: str | None = None

    def fresh_assessment(self, job_id: str) -> FinalizationAssessment:
        return self._assessment_service.assess(job_id)

    def begin(
        self,
        *,
        job_id: str,
        operation,
        requested_by: str,
        source: str,
        assessment: FinalizationAssessment,
        dry_run: bool,
    ) -> RecoveryResult | None:
        if dry_run:
            return None
        now = self._clock.now()
        self._recovery_id = str(uuid.uuid4())
        try:
            attempt = self._recovery_store.begin_attempt(
                recovery_id=self._recovery_id,
                job_id=job_id,
                operation=operation,
                requested_by=requested_by,
                source=source,
                initial_assessment_outcome=assessment.outcome.value,
                initial_blocking_reason=assessment.blocking_reason,
                lease_expires_at=now + timedelta(seconds=self._lease_seconds),
                now=now,
            )
        except RecoveryLeaseConflictError as exc:
            new_assessment = self.fresh_assessment(job_id)
            return RecoveryResult(
                job_id=job_id,
                operation=operation,
                outcome=RecoveryOutcome.CONCURRENCY_CONFLICT,
                previous_assessment=assessment,
                new_assessment=new_assessment,
                error_code="recovery_lease_conflict",
                sanitized_message=sanitize_recovery_message(str(exc)),
            )
        self._attempt_id = attempt.id
        return None

    def finish(
        self,
        *,
        outcome: RecoveryOutcome,
        previous: FinalizationAssessment,
        new: FinalizationAssessment,
        operation,
        job_id: str,
        error_code: str | None = None,
        sanitized_message: str | None = None,
        dry_run: bool = False,
        stages_attempted=(),
        stages_completed=(),
        stages_skipped=(),
    ) -> RecoveryResult:
        if not dry_run and self._attempt_id is not None:
            status = RecoveryAttemptStatus.SUCCEEDED
            if outcome in (RecoveryOutcome.FAILED, RecoveryOutcome.NOT_ELIGIBLE):
                status = RecoveryAttemptStatus.FAILED
            elif outcome == RecoveryOutcome.PARTIALLY_RECOVERED:
                status = RecoveryAttemptStatus.PARTIAL
            elif outcome in (
                RecoveryOutcome.CONCURRENCY_CONFLICT,
                RecoveryOutcome.INCONSISTENT,
                RecoveryOutcome.NOT_ELIGIBLE,
            ):
                status = RecoveryAttemptStatus.REJECTED
            self._recovery_store.finish_attempt(
                attempt_id=self._attempt_id,
                status=status.value,
                final_assessment_outcome=new.outcome.value,
                final_blocking_reason=new.blocking_reason,
                error_code=error_code,
                sanitized_error=sanitize_recovery_message(sanitized_message),
                now=self._clock.now(),
            )
        return RecoveryResult(
            job_id=job_id,
            operation=operation,
            outcome=outcome,
            previous_assessment=previous,
            new_assessment=new,
            stages_attempted=stages_attempted,
            stages_completed=stages_completed,
            stages_skipped=stages_skipped,
            error_code=error_code,
            sanitized_message=sanitize_recovery_message(sanitized_message),
            dry_run=dry_run,
            recovery_id=self._recovery_id,
            eligible_operations=self._eligibility.eligible_operations(
                new, self._job_repo.get_by_id(job_id)
            ),
            blocked_operations=self._eligibility.blocked_operations(
                new, self._job_repo.get_by_id(job_id)
            ),
        )

    def build_dry_run_result(
        self,
        *,
        job_id: str,
        operation,
        assessment: FinalizationAssessment,
        job,
        predicted_next_stage,
        artifact_sources=(),
    ) -> RecoveryResult:
        return RecoveryResult(
            job_id=job_id,
            operation=operation,
            outcome=RecoveryOutcome.VERIFICATION_REQUIRED,
            previous_assessment=assessment,
            new_assessment=assessment,
            dry_run=True,
            eligible_operations=self._eligibility.eligible_operations(assessment, job),
            blocked_operations=self._eligibility.blocked_operations(assessment, job),
        )
