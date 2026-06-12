"""Recovery eligibility and assessment gate — Phase 3.4."""

from __future__ import annotations

from src.domain.jobs.entities import Job, JobStatus
from src.domain.jobs.finalization_evidence import (
    FINALIZATION_STAGE_ORDER,
    FinalizationAssessment,
    FinalizationAssessmentOutcome,
    FinalizationStage,
    StageStatus,
)
from src.domain.jobs.finalization_recovery import RecoveryOperation


_VERIFY_ALLOWED_OUTCOMES = frozenset(
    {
        FinalizationAssessmentOutcome.VERIFICATION_REQUIRED,
        FinalizationAssessmentOutcome.DOMAIN_COMMITTED_ARTIFACTS_MISSING,
        FinalizationAssessmentOutcome.ARTIFACTS_COMPLETE_TERMINALIZATION_MISSING,
        FinalizationAssessmentOutcome.TECHNICALLY_SUCCEEDED_RECONCILIATION_PENDING,
        FinalizationAssessmentOutcome.INCONSISTENT,
    }
)

_OPERATION_TO_OUTCOMES: dict[RecoveryOperation, frozenset[FinalizationAssessmentOutcome]] = {
    RecoveryOperation.VERIFY: _VERIFY_ALLOWED_OUTCOMES,
    RecoveryOperation.REPUBLISH_ARTIFACTS: frozenset(
        {
            FinalizationAssessmentOutcome.DOMAIN_COMMITTED_ARTIFACTS_MISSING,
            FinalizationAssessmentOutcome.VERIFICATION_REQUIRED,
        }
    ),
    RecoveryOperation.TERMINALIZE: frozenset(
        {
            FinalizationAssessmentOutcome.ARTIFACTS_COMPLETE_TERMINALIZATION_MISSING,
            FinalizationAssessmentOutcome.VERIFICATION_REQUIRED,
        }
    ),
    RecoveryOperation.PROMOTE: frozenset(
        {FinalizationAssessmentOutcome.TECHNICALLY_SUCCEEDED_RECONCILIATION_PENDING}
    ),
    RecoveryOperation.RECONCILE_AISLE: frozenset(
        {FinalizationAssessmentOutcome.TECHNICALLY_SUCCEEDED_RECONCILIATION_PENDING}
    ),
    RecoveryOperation.RECONCILE_INVENTORY: frozenset(
        {FinalizationAssessmentOutcome.TECHNICALLY_SUCCEEDED_RECONCILIATION_PENDING}
    ),
    RecoveryOperation.RESUME: frozenset(
        {
            FinalizationAssessmentOutcome.DOMAIN_COMMITTED_ARTIFACTS_MISSING,
            FinalizationAssessmentOutcome.ARTIFACTS_COMPLETE_TERMINALIZATION_MISSING,
            FinalizationAssessmentOutcome.TECHNICALLY_SUCCEEDED_RECONCILIATION_PENDING,
            FinalizationAssessmentOutcome.VERIFICATION_REQUIRED,
        }
    ),
}


class FinalizationRecoveryEligibility:
    """Assessment-first gate for manual recovery operations."""

    def is_stage_completed(
        self, assessment: FinalizationAssessment, stage: FinalizationStage
    ) -> bool:
        view = assessment.stages.get(stage.value)
        return view is not None and view.status == StageStatus.COMPLETED

    def refuse_global_assessment(
        self,
        assessment: FinalizationAssessment,
        operation: RecoveryOperation,
    ) -> str | None:
        if assessment.outcome == FinalizationAssessmentOutcome.COMPLETE:
            return "already_complete"
        if assessment.outcome == FinalizationAssessmentOutcome.FAILED_BEFORE_DOMAIN_COMMIT:
            return "failed_before_domain_commit"
        if assessment.outcome == FinalizationAssessmentOutcome.INCONSISTENT:
            if operation != RecoveryOperation.VERIFY:
                return "inconsistent_assessment"
        allowed = _OPERATION_TO_OUTCOMES.get(operation, frozenset())
        if assessment.outcome not in allowed and operation != RecoveryOperation.VERIFY:
            return f"assessment_outcome_{assessment.outcome.value}"
        return None

    def cancellation_blocks_recovery(
        self,
        job: Job,
        assessment: FinalizationAssessment,
        *,
        allow_canceled_terminalization: bool = False,
    ) -> str | None:
        if job.status != JobStatus.CANCELED:
            return None
        if self.is_stage_completed(assessment, FinalizationStage.DOMAIN_RESULTS):
            if allow_canceled_terminalization:
                return None
            return "canceled_after_domain_commit_requires_explicit_override"
        return "canceled_before_domain_commit"

    def stage_precondition_met(
        self,
        assessment: FinalizationAssessment,
        required_stage: FinalizationStage,
    ) -> bool:
        return self.is_stage_completed(assessment, required_stage)

    def eligible_operations(
        self, assessment: FinalizationAssessment, job: Job | None
    ) -> tuple[RecoveryOperation, ...]:
        if job is None:
            return ()
        if assessment.outcome == FinalizationAssessmentOutcome.COMPLETE:
            return ()
        eligible: list[RecoveryOperation] = []
        for op in RecoveryOperation:
            if op == RecoveryOperation.RESUME:
                continue
            if self.refuse_global_assessment(assessment, op) is None:
                if self.cancellation_blocks_recovery(job, assessment) is None:
                    if self._operation_preconditions(op, assessment, job):
                        eligible.append(op)
        if eligible:
            eligible.append(RecoveryOperation.RESUME)
        return tuple(eligible)

    def blocked_operations(
        self, assessment: FinalizationAssessment, job: Job | None
    ) -> tuple[RecoveryOperation, ...]:
        all_ops = tuple(RecoveryOperation)
        eligible = set(self.eligible_operations(assessment, job))
        return tuple(op for op in all_ops if op not in eligible)

    def first_incomplete_stage(
        self, assessment: FinalizationAssessment
    ) -> FinalizationStage | None:
        if assessment.next_required_stage is not None:
            return assessment.next_required_stage
        for stage in FINALIZATION_STAGE_ORDER:
            view = assessment.stages.get(stage.value)
            if view is None or view.status != StageStatus.COMPLETED:
                return stage
        return None

    def resume_operation_for_stage(
        self, stage: FinalizationStage
    ) -> RecoveryOperation | None:
        mapping = {
            FinalizationStage.REQUIRED_ARTIFACTS: RecoveryOperation.REPUBLISH_ARTIFACTS,
            FinalizationStage.JOB_TERMINALIZATION: RecoveryOperation.TERMINALIZE,
            FinalizationStage.OPERATIONAL_PROMOTION: RecoveryOperation.PROMOTE,
            FinalizationStage.AISLE_RECONCILIATION: RecoveryOperation.RECONCILE_AISLE,
            FinalizationStage.INVENTORY_RECONCILIATION: RecoveryOperation.RECONCILE_INVENTORY,
        }
        return mapping.get(stage)

    def _operation_preconditions(
        self,
        operation: RecoveryOperation,
        assessment: FinalizationAssessment,
        job: Job,
    ) -> bool:
        if operation == RecoveryOperation.VERIFY:
            return True
        if operation == RecoveryOperation.REPUBLISH_ARTIFACTS:
            return self.stage_precondition_met(assessment, FinalizationStage.DOMAIN_RESULTS)
        if operation == RecoveryOperation.TERMINALIZE:
            return (
                self.stage_precondition_met(assessment, FinalizationStage.DOMAIN_RESULTS)
                and job.status in (JobStatus.SUCCEEDED, JobStatus.RUNNING, JobStatus.CANCELED)
            )
        if operation == RecoveryOperation.PROMOTE:
            return (
                job.status == JobStatus.SUCCEEDED
                and self.stage_precondition_met(assessment, FinalizationStage.JOB_TERMINALIZATION)
            )
        if operation == RecoveryOperation.RECONCILE_AISLE:
            return job.status == JobStatus.SUCCEEDED
        if operation == RecoveryOperation.RECONCILE_INVENTORY:
            return self.stage_precondition_met(assessment, FinalizationStage.AISLE_RECONCILIATION)
        if operation == RecoveryOperation.RESUME:
            return self.first_incomplete_stage(assessment) is not None
        return False
