"""Shared recovery result helpers — Phase 3.4."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.services.finalization_recovery_eligibility import (
    FinalizationRecoveryEligibility,
)
from src.application.services.finalization_recovery_support import (
    RecoverySession,
    sanitize_recovery_message,
)
from src.application.use_cases.finalization_recovery.recovery_command import RecoveryCommand
from src.domain.jobs.finalization_recovery import RecoveryOperation, RecoveryOutcome, RecoveryResult

if TYPE_CHECKING:
    from src.application.services.finalization_assessment_service import FinalizationAssessment
    from src.application.use_cases.finalization_recovery.verify_and_republish import (
        FinalizationRecoveryDependencies,
    )
    from src.domain.jobs.entities import Job


def make_recovery_result(
    command: RecoveryCommand,
    previous: FinalizationAssessment,
    new: FinalizationAssessment,
    outcome: RecoveryOutcome,
    operation: RecoveryOperation,
    deps: FinalizationRecoveryDependencies,
    *,
    error_code: str | None = None,
    sanitized_message: str | None = None,
    stages_attempted=(),
    stages_completed=(),
    stages_skipped=(),
    recovery_id: str | None = None,
) -> RecoveryResult:
    eligibility = deps.eligibility or FinalizationRecoveryEligibility()
    job = deps.job_repo.get_by_id(command.job_id)
    return RecoveryResult(
        job_id=command.job_id,
        operation=operation,
        outcome=outcome,
        previous_assessment=previous,
        new_assessment=new,
        stages_attempted=stages_attempted,
        stages_completed=stages_completed,
        stages_skipped=stages_skipped,
        error_code=error_code,
        sanitized_message=sanitize_recovery_message(sanitized_message),
        dry_run=command.dry_run,
        recovery_id=recovery_id
        or (command.execution_context.recovery_id if command.execution_context else None),
        eligible_operations=eligibility.eligible_operations(new, job),
        blocked_operations=eligibility.blocked_operations(new, job),
    )


def not_eligible(
    command: RecoveryCommand,
    assessment: FinalizationAssessment,
    operation: RecoveryOperation,
    code: str,
    deps: FinalizationRecoveryDependencies,
) -> RecoveryResult:
    return make_recovery_result(
        command,
        assessment,
        assessment,
        RecoveryOutcome.NOT_ELIGIBLE,
        operation,
        deps,
        error_code=code,
    )


def gate_or_dry_run(
    command: RecoveryCommand,
    assessment: FinalizationAssessment,
    job: Job,
    operation: RecoveryOperation,
    eligibility: FinalizationRecoveryEligibility,
    deps: FinalizationRecoveryDependencies,
) -> RecoveryResult | None:
    blocked = eligibility.refuse_global_assessment(assessment, operation)
    if blocked:
        outcome = RecoveryOutcome.NOT_ELIGIBLE
        if blocked == "inconsistent_assessment":
            outcome = RecoveryOutcome.INCONSISTENT
        elif blocked == "already_complete":
            outcome = RecoveryOutcome.ALREADY_COMPLETE
        elif blocked == "failed_before_domain_commit":
            outcome = RecoveryOutcome.NOT_ELIGIBLE
        return make_recovery_result(
            command,
            assessment,
            assessment,
            outcome,
            operation,
            deps,
            error_code=blocked,
        )
    cancel = eligibility.cancellation_blocks_recovery(
        job,
        assessment,
        allow_canceled_terminalization=command.allow_canceled_terminalization,
    )
    if cancel:
        return not_eligible(command, assessment, operation, cancel, deps)
    if command.dry_run:
        return make_recovery_result(
            command,
            assessment,
            assessment,
            RecoveryOutcome.VERIFICATION_REQUIRED,
            operation,
            deps,
        )
    return None


def begin_recovery_lease(
    session: RecoverySession,
    command: RecoveryCommand,
    *,
    job_id: str,
    operation: RecoveryOperation,
    requested_by: str,
    source: str,
    assessment: FinalizationAssessment,
    dry_run: bool,
) -> RecoveryResult | None:
    if command.lease_exempt:
        return None
    return session.begin(
        job_id=job_id,
        operation=operation,
        requested_by=requested_by,
        source=source,
        assessment=assessment,
        dry_run=dry_run,
    )


def finish_recovery_lease(
    session: RecoverySession,
    command: RecoveryCommand,
    deps: FinalizationRecoveryDependencies,
    *,
    outcome: RecoveryOutcome,
    previous: FinalizationAssessment,
    new: FinalizationAssessment,
    operation: RecoveryOperation,
    job_id: str,
    error_code: str | None = None,
    sanitized_message: str | None = None,
    dry_run: bool = False,
    stages_attempted=(),
    stages_completed=(),
    stages_skipped=(),
) -> RecoveryResult:
    if command.lease_exempt:
        return make_recovery_result(
            command,
            previous,
            new,
            outcome,
            operation,
            deps,
            error_code=error_code,
            sanitized_message=sanitized_message,
            stages_attempted=stages_attempted,
            stages_completed=stages_completed,
            stages_skipped=stages_skipped,
        )
    return session.finish(
        outcome=outcome,
        previous=previous,
        new=new,
        operation=operation,
        job_id=job_id,
        error_code=error_code,
        sanitized_message=sanitized_message,
        dry_run=dry_run,
        stages_attempted=stages_attempted,
        stages_completed=stages_completed,
        stages_skipped=stages_skipped,
    )
