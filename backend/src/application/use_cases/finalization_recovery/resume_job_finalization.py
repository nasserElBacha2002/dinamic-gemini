"""Coordinated resume recovery — Phase 3.4."""

from __future__ import annotations

from src.application.services.finalization_recovery_eligibility import (
    FinalizationRecoveryEligibility,
)
from src.application.use_cases.finalization_recovery.recovery_command import (
    RecoveryCommand,
    RecoveryExecutionContext,
)
from src.application.use_cases.finalization_recovery.recovery_helpers import (
    begin_recovery_lease,
    finish_recovery_lease,
    gate_or_dry_run,
    make_recovery_result,
    not_eligible,
)
from src.application.use_cases.finalization_recovery.terminalize_promote_reconcile import (
    PromoteRecoveredOperationalResultUseCase,
    ReconcileRecoveredAisleUseCase,
    ReconcileRecoveredInventoryUseCase,
    TerminalizeRecoveredJobUseCase,
)
from src.application.use_cases.finalization_recovery.verify_and_republish import (
    FinalizationRecoveryDependencies,
    RepublishJobArtifactsUseCase,
    VerifyJobFinalizationUseCase,
)
from src.domain.jobs.finalization_evidence import FINALIZATION_STAGE_ORDER, FinalizationStage
from src.domain.jobs.finalization_recovery import RecoveryOperation, RecoveryOutcome, RecoveryResult

_OP_TO_STAGE = {
    RecoveryOperation.REPUBLISH_ARTIFACTS: FinalizationStage.REQUIRED_ARTIFACTS,
    RecoveryOperation.TERMINALIZE: FinalizationStage.JOB_TERMINALIZATION,
    RecoveryOperation.PROMOTE: FinalizationStage.OPERATIONAL_PROMOTION,
    RecoveryOperation.RECONCILE_AISLE: FinalizationStage.AISLE_RECONCILIATION,
    RecoveryOperation.RECONCILE_INVENTORY: FinalizationStage.INVENTORY_RECONCILIATION,
}


class ResumeJobFinalizationUseCase:
    operation = RecoveryOperation.RESUME

    def __init__(self, deps: FinalizationRecoveryDependencies) -> None:
        self._deps = deps
        self._eligibility = deps.eligibility or FinalizationRecoveryEligibility()
        self._verify = VerifyJobFinalizationUseCase(deps)
        self._republish = RepublishJobArtifactsUseCase(deps)
        self._terminalize = TerminalizeRecoveredJobUseCase(deps)
        self._promote = PromoteRecoveredOperationalResultUseCase(deps)
        self._reconcile_aisle = ReconcileRecoveredAisleUseCase(deps)
        self._reconcile_inventory = ReconcileRecoveredInventoryUseCase(deps)
        self._use_cases = {
            RecoveryOperation.REPUBLISH_ARTIFACTS: self._republish,
            RecoveryOperation.TERMINALIZE: self._terminalize,
            RecoveryOperation.PROMOTE: self._promote,
            RecoveryOperation.RECONCILE_AISLE: self._reconcile_aisle,
            RecoveryOperation.RECONCILE_INVENTORY: self._reconcile_inventory,
        }

    def execute(self, command: RecoveryCommand) -> RecoveryResult:
        assessment = self._deps.assessment_service.assess(command.job_id)
        job = self._deps.job_repo.get_by_id(command.job_id)
        if job is None:
            return not_eligible(command, assessment, self.operation, "job_not_found", self._deps)
        gate = gate_or_dry_run(command, assessment, job, self.operation, self._eligibility, self._deps)
        if gate is not None:
            return gate
        first = self._eligibility.first_incomplete_stage(assessment)
        if first is None:
            return make_recovery_result(
                command, assessment, assessment, RecoveryOutcome.ALREADY_COMPLETE, self.operation, self._deps
            )
        start_idx = FINALIZATION_STAGE_ORDER.index(first)
        steps: list[tuple[RecoveryOperation, object]] = []
        for stage in FINALIZATION_STAGE_ORDER[start_idx:]:
            op = self._eligibility.resume_operation_for_stage(stage)
            if op is not None and op in self._use_cases:
                steps.append((op, self._use_cases[op]))
        if not steps:
            return self._verify.execute(
                RecoveryCommand(
                    job_id=command.job_id,
                    requested_by=command.requested_by,
                    source=command.source,
                    allow_canceled_terminalization=command.allow_canceled_terminalization,
                )
            )

        session = self._deps.session()
        conflict = begin_recovery_lease(
            session,
            command,
            job_id=command.job_id,
            operation=self.operation,
            requested_by=command.requested_by,
            source=command.source,
            assessment=assessment,
            dry_run=False,
        )
        if conflict is not None:
            return conflict
        assert session.recovery_id is not None and session.attempt_id is not None
        child_context = RecoveryExecutionContext(
            recovery_id=session.recovery_id,
            attempt_id=session.attempt_id,
            requested_by=command.requested_by,
            source=command.source,
        )

        attempted: list[RecoveryOperation] = []
        completed: list[RecoveryOperation] = []
        attempted_stages: list[FinalizationStage] = []
        completed_stages: list[FinalizationStage] = []
        current_assessment = assessment
        for op, use_case in steps:
            step_cmd = RecoveryCommand(
                job_id=command.job_id,
                requested_by=command.requested_by,
                source=command.source,
                allow_canceled_terminalization=command.allow_canceled_terminalization,
                execution_context=child_context,
            )
            result = use_case.execute(step_cmd)
            current_assessment = result.new_assessment
            attempted.append(op)
            stage = _OP_TO_STAGE.get(op)
            if stage is not None:
                attempted_stages.append(stage)
            if result.outcome in (
                RecoveryOutcome.RECOVERED,
                RecoveryOutcome.ALREADY_COMPLETE,
                RecoveryOutcome.ALREADY_OPERATIONAL,
            ):
                completed.append(op)
                if stage is not None:
                    completed_stages.append(stage)
                continue
            if result.outcome in (RecoveryOutcome.ALREADY_SUPERSEDED, RecoveryOutcome.VERIFICATION_REQUIRED):
                continue
            return finish_recovery_lease(
                session,
                command,
                self._deps,
                outcome=RecoveryOutcome.PARTIALLY_RECOVERED,
                previous=assessment,
                new=current_assessment,
                operation=self.operation,
                job_id=command.job_id,
                error_code=result.error_code,
                sanitized_message=result.sanitized_message,
                stages_attempted=tuple(attempted_stages),
                stages_completed=tuple(completed_stages),
            )
        final = self._deps.assessment_service.assess(command.job_id)
        outcome = (
            RecoveryOutcome.RECOVERED
            if final.outcome.value == "complete"
            else RecoveryOutcome.PARTIALLY_RECOVERED
        )
        return finish_recovery_lease(
            session,
            command,
            self._deps,
            outcome=outcome,
            previous=assessment,
            new=final,
            operation=self.operation,
            job_id=command.job_id,
            stages_attempted=tuple(attempted_stages),
            stages_completed=tuple(completed_stages),
        )


class FinalizationRecoveryCoordinator:
    """Route explicit recovery operations to focused use cases."""

    def __init__(self, deps: FinalizationRecoveryDependencies) -> None:
        self._deps = deps
        self._handlers = {
            RecoveryOperation.VERIFY: VerifyJobFinalizationUseCase(deps),
            RecoveryOperation.REPUBLISH_ARTIFACTS: RepublishJobArtifactsUseCase(deps),
            RecoveryOperation.TERMINALIZE: TerminalizeRecoveredJobUseCase(deps),
            RecoveryOperation.PROMOTE: PromoteRecoveredOperationalResultUseCase(deps),
            RecoveryOperation.RECONCILE_AISLE: ReconcileRecoveredAisleUseCase(deps),
            RecoveryOperation.RECONCILE_INVENTORY: ReconcileRecoveredInventoryUseCase(deps),
            RecoveryOperation.RESUME: ResumeJobFinalizationUseCase(deps),
        }

    def execute(self, operation: RecoveryOperation, command: RecoveryCommand) -> RecoveryResult:
        handler = self._handlers.get(operation)
        if handler is None:
            assessment = self._deps.assessment_service.assess(command.job_id)
            return make_recovery_result(
                command,
                assessment,
                assessment,
                RecoveryOutcome.NOT_ELIGIBLE,
                operation,
                self._deps,
                error_code="unknown_operation",
            )
        return handler.execute(command)
