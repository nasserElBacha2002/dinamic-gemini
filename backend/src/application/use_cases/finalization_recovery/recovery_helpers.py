"""Shared recovery result helpers — Phase 3.4."""

from __future__ import annotations

from src.application.services.finalization_recovery_eligibility import FinalizationRecoveryEligibility
from src.application.services.finalization_recovery_support import sanitize_recovery_message
from src.application.use_cases.finalization_recovery.recovery_command import RecoveryCommand
from src.domain.jobs.finalization_recovery import RecoveryOperation, RecoveryOutcome, RecoveryResult


def make_recovery_result(
    command: RecoveryCommand,
    previous,
    new,
    outcome: RecoveryOutcome,
    operation: RecoveryOperation,
    deps,
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
        recovery_id=recovery_id,
        eligible_operations=eligibility.eligible_operations(new, job),
        blocked_operations=eligibility.blocked_operations(new, job),
    )


def not_eligible(command, assessment, operation, code, deps):
    return make_recovery_result(
        command,
        assessment,
        assessment,
        RecoveryOutcome.NOT_ELIGIBLE,
        operation,
        deps,
        error_code=code,
    )


def gate_or_dry_run(command, assessment, job, operation, eligibility, deps):
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
