"""Terminalization, promotion, and reconciliation recovery — Phase 3.4."""

from __future__ import annotations

import logging

from src.application.ports.operational_job_promotion import PromotionOutcome
from src.application.use_cases.finalization_recovery.recovery_command import RecoveryCommand
from src.application.use_cases.finalization_recovery.recovery_helpers import (
    gate_or_dry_run,
    make_recovery_result,
    not_eligible,
)
from src.application.use_cases.finalization_recovery.verify_and_republish import (
    FinalizationRecoveryDependencies,
)
from src.domain.jobs.entities import JobStatus
from src.domain.jobs.finalization import LastCompletedFinalizationStep
from src.domain.jobs.finalization_evidence import (
    ArtifactVerificationVerdict,
    EvidenceLevel,
    FinalizationStage,
    StageStatus,
)
from src.domain.jobs.finalization_recovery import RecoveryOperation, RecoveryOutcome
from src.infrastructure.pipeline.worker_durable_artifact_publisher import merge_durable_into_result_json

logger = logging.getLogger(__name__)


class TerminalizeRecoveredJobUseCase:
    operation = RecoveryOperation.TERMINALIZE

    def __init__(self, deps: FinalizationRecoveryDependencies) -> None:
        self._deps = deps
        self._eligibility = deps.eligibility

    def execute(self, command: RecoveryCommand):
        from src.application.services.finalization_recovery_eligibility import (
            FinalizationRecoveryEligibility,
        )

        eligibility = self._eligibility or FinalizationRecoveryEligibility()
        assessment = self._deps.assessment_service.assess(command.job_id)
        job = self._deps.job_repo.get_by_id(command.job_id)
        if job is None:
            return not_eligible(command, assessment, self.operation, "job_not_found", self._deps)
        terminal_stage = self._deps.stage_store.get_stage(
            command.job_id, FinalizationStage.JOB_TERMINALIZATION
        )
        if (
            job.status == JobStatus.SUCCEEDED
            and terminal_stage is not None
            and terminal_stage.status == StageStatus.COMPLETED
        ):
            return make_recovery_result(
                command,
                assessment,
                assessment,
                RecoveryOutcome.ALREADY_COMPLETE,
                self.operation,
                self._deps,
            )
        gate = gate_or_dry_run(command, assessment, job, self.operation, eligibility, self._deps)
        if gate is not None:
            return gate
        if not eligibility.stage_precondition_met(assessment, FinalizationStage.DOMAIN_RESULTS):
            return not_eligible(
                command, assessment, self.operation, "domain_results_not_completed", self._deps
            )
        checks = self._deps.artifact_verifier.verify_required(command.job_id)
        if not all(c.verdict == ArtifactVerificationVerdict.CONFIRMED for c in checks):
            return not_eligible(
                command, assessment, self.operation, "required_artifacts_not_verified", self._deps
            )
        session = self._deps.session()
        conflict = session.begin(
            job_id=command.job_id,
            operation=self.operation,
            requested_by=command.requested_by,
            source=command.source,
            assessment=assessment,
            dry_run=False,
        )
        if conflict is not None:
            return conflict
        now = self._deps.clock.now()
        job.status = JobStatus.SUCCEEDED
        job.finished_at = job.finished_at or now
        job.updated_at = now
        job.error_message = None
        job.failure_code = None
        job.failure_message = None
        job.finalization_error_code = None
        durable = (job.result_json or {}).get("durable_artifacts")
        if isinstance(durable, dict):
            merge_durable_into_result_json(job.result_json or {}, durable)
        self._deps.job_repo.save(job)
        recorder = self._deps.recorder()
        recorder.mark_completed_for_step(
            command.job_id,
            LastCompletedFinalizationStep.JOB_TERMINALIZED,
            evidence_level=EvidenceLevel.CONFIRMED,
            verification_source="recovery_terminalize",
        )
        new_assessment = session.fresh_assessment(command.job_id)
        return session.finish(
            outcome=RecoveryOutcome.RECOVERED,
            previous=assessment,
            new=new_assessment,
            operation=self.operation,
            job_id=command.job_id,
            stages_attempted=(FinalizationStage.JOB_TERMINALIZATION,),
            stages_completed=(FinalizationStage.JOB_TERMINALIZATION,),
        )


class PromoteRecoveredOperationalResultUseCase:
    operation = RecoveryOperation.PROMOTE

    def __init__(self, deps: FinalizationRecoveryDependencies) -> None:
        self._deps = deps
        self._eligibility = deps.eligibility

    def execute(self, command: RecoveryCommand):
        from src.application.services.finalization_recovery_eligibility import (
            FinalizationRecoveryEligibility,
        )

        eligibility = self._eligibility or FinalizationRecoveryEligibility()
        assessment = self._deps.assessment_service.assess(command.job_id)
        job = self._deps.job_repo.get_by_id(command.job_id)
        if job is None:
            return not_eligible(command, assessment, self.operation, "job_not_found", self._deps)
        gate = gate_or_dry_run(command, assessment, job, self.operation, eligibility, self._deps)
        if gate is not None:
            return gate
        if job.status != JobStatus.SUCCEEDED:
            return not_eligible(command, assessment, self.operation, "job_not_succeeded", self._deps)
        if job.target_type != "aisle" or not job.target_id:
            return not_eligible(command, assessment, self.operation, "invalid_job_target", self._deps)
        aisle = self._deps.aisle_repo.get_by_id(job.target_id)
        if aisle is None:
            return not_eligible(command, assessment, self.operation, "aisle_not_found", self._deps)
        if aisle.operational_job_id == command.job_id:
            return make_recovery_result(
                command,
                assessment,
                assessment,
                RecoveryOutcome.ALREADY_OPERATIONAL,
                self.operation,
                self._deps,
            )
        session = self._deps.session()
        conflict = session.begin(
            job_id=command.job_id,
            operation=self.operation,
            requested_by=command.requested_by,
            source=command.source,
            assessment=assessment,
            dry_run=False,
        )
        if conflict is not None:
            return conflict
        promotion = self._deps.promotion_service.promote_for_success(
            aisle_id=aisle.id,
            candidate_job_id=command.job_id,
        )
        if promotion.outcome == PromotionOutcome.REJECTED_STALE:
            return session.finish(
                outcome=RecoveryOutcome.ALREADY_SUPERSEDED,
                previous=assessment,
                new=session.fresh_assessment(command.job_id),
                operation=self.operation,
                job_id=command.job_id,
                error_code="newer_operational_job_exists",
            )
        if promotion.outcome == PromotionOutcome.ALREADY_OPERATIONAL:
            outcome = RecoveryOutcome.ALREADY_OPERATIONAL
        elif promotion.outcome == PromotionOutcome.PROMOTED:
            outcome = RecoveryOutcome.RECOVERED
        else:
            return session.finish(
                outcome=RecoveryOutcome.NOT_ELIGIBLE,
                previous=assessment,
                new=session.fresh_assessment(command.job_id),
                operation=self.operation,
                job_id=command.job_id,
                error_code=promotion.outcome.value,
            )
        recorder = self._deps.recorder()
        recorder.mark_completed_for_step(
            command.job_id,
            LastCompletedFinalizationStep.OPERATIONAL_RESULT_PROMOTED,
            evidence_level=EvidenceLevel.CONFIRMED,
            verification_source="recovery_promote",
        )
        new_assessment = session.fresh_assessment(command.job_id)
        return session.finish(
            outcome=outcome,
            previous=assessment,
            new=new_assessment,
            operation=self.operation,
            job_id=command.job_id,
            stages_attempted=(FinalizationStage.OPERATIONAL_PROMOTION,),
            stages_completed=(FinalizationStage.OPERATIONAL_PROMOTION,),
        )


class ReconcileRecoveredAisleUseCase:
    operation = RecoveryOperation.RECONCILE_AISLE

    def __init__(self, deps: FinalizationRecoveryDependencies) -> None:
        self._deps = deps

    def execute(self, command: RecoveryCommand):
        from src.application.services.finalization_recovery_eligibility import (
            FinalizationRecoveryEligibility,
        )

        eligibility = self._deps.eligibility or FinalizationRecoveryEligibility()
        assessment = self._deps.assessment_service.assess(command.job_id)
        job = self._deps.job_repo.get_by_id(command.job_id)
        if job is None:
            return not_eligible(command, assessment, self.operation, "job_not_found", self._deps)
        gate = gate_or_dry_run(command, assessment, job, self.operation, eligibility, self._deps)
        if gate is not None:
            return gate
        if job.target_type != "aisle" or not job.target_id:
            return not_eligible(command, assessment, self.operation, "invalid_job_target", self._deps)
        aisle = self._deps.aisle_repo.get_by_id(job.target_id)
        if aisle is None:
            return not_eligible(command, assessment, self.operation, "aisle_not_found", self._deps)
        aisle_stage = self._deps.stage_store.get_stage(
            command.job_id, FinalizationStage.AISLE_RECONCILIATION
        )
        if aisle_stage and aisle_stage.status == StageStatus.COMPLETED:
            return make_recovery_result(
                command,
                assessment,
                assessment,
                RecoveryOutcome.ALREADY_COMPLETE,
                self.operation,
                self._deps,
            )
        session = self._deps.session()
        conflict = session.begin(
            job_id=command.job_id,
            operation=self.operation,
            requested_by=command.requested_by,
            source=command.source,
            assessment=assessment,
            dry_run=False,
        )
        if conflict is not None:
            return conflict
        now = self._deps.clock.now()
        if aisle.operational_job_id and aisle.operational_job_id != command.job_id:
            op = self._deps.job_repo.get_by_id(aisle.operational_job_id)
            if op and op.status == JobStatus.SUCCEEDED and op.created_at > job.created_at:
                return session.finish(
                    outcome=RecoveryOutcome.ALREADY_SUPERSEDED,
                    previous=assessment,
                    new=session.fresh_assessment(command.job_id),
                    operation=self.operation,
                    job_id=command.job_id,
                    error_code="newer_operational_aisle_state",
                )
        aisle.mark_processed(now)
        self._deps.aisle_repo.save(aisle)
        recorder = self._deps.recorder()
        recorder.mark_completed_for_step(
            command.job_id,
            LastCompletedFinalizationStep.AISLE_UPDATED,
            evidence_level=EvidenceLevel.CONFIRMED,
            verification_source="recovery_aisle_reconcile",
        )
        new_assessment = session.fresh_assessment(command.job_id)
        return session.finish(
            outcome=RecoveryOutcome.RECOVERED,
            previous=assessment,
            new=new_assessment,
            operation=self.operation,
            job_id=command.job_id,
            stages_attempted=(FinalizationStage.AISLE_RECONCILIATION,),
            stages_completed=(FinalizationStage.AISLE_RECONCILIATION,),
        )


class ReconcileRecoveredInventoryUseCase:
    operation = RecoveryOperation.RECONCILE_INVENTORY

    def __init__(self, deps: FinalizationRecoveryDependencies) -> None:
        self._deps = deps

    def execute(self, command: RecoveryCommand):
        from src.application.services.finalization_recovery_eligibility import (
            FinalizationRecoveryEligibility,
        )

        eligibility = self._deps.eligibility or FinalizationRecoveryEligibility()
        assessment = self._deps.assessment_service.assess(command.job_id)
        job = self._deps.job_repo.get_by_id(command.job_id)
        if job is None:
            return not_eligible(command, assessment, self.operation, "job_not_found", self._deps)
        gate = gate_or_dry_run(command, assessment, job, self.operation, eligibility, self._deps)
        if gate is not None:
            return gate
        if not eligibility.stage_precondition_met(
            assessment, FinalizationStage.AISLE_RECONCILIATION
        ):
            return not_eligible(
                command, assessment, self.operation, "aisle_reconciliation_not_completed", self._deps
            )
        inv_stage = self._deps.stage_store.get_stage(
            command.job_id, FinalizationStage.INVENTORY_RECONCILIATION
        )
        if inv_stage and inv_stage.status == StageStatus.COMPLETED:
            new = assessment
            outcome = (
                RecoveryOutcome.ALREADY_COMPLETE
                if new.outcome == assessment.outcome
                else RecoveryOutcome.RECOVERED
            )
            return make_recovery_result(
                command, assessment, new, outcome, self.operation, self._deps
            )
        if job.target_type != "aisle" or not job.target_id:
            return not_eligible(command, assessment, self.operation, "invalid_job_target", self._deps)
        aisle = self._deps.aisle_repo.get_by_id(job.target_id)
        if aisle is None:
            return not_eligible(command, assessment, self.operation, "aisle_not_found", self._deps)
        session = self._deps.session()
        conflict = session.begin(
            job_id=command.job_id,
            operation=self.operation,
            requested_by=command.requested_by,
            source=command.source,
            assessment=assessment,
            dry_run=False,
        )
        if conflict is not None:
            return conflict
        self._deps.inventory_reconciler.reconcile(aisle.inventory_id)
        recorder = self._deps.recorder()
        recorder.mark_completed_for_step(
            command.job_id,
            LastCompletedFinalizationStep.INVENTORY_RECONCILED,
            evidence_level=EvidenceLevel.CONFIRMED,
            verification_source="recovery_inventory_reconcile",
        )
        new_assessment = session.fresh_assessment(command.job_id)
        outcome = (
            RecoveryOutcome.RECOVERED
            if new_assessment.outcome.value == "complete"
            else RecoveryOutcome.VERIFICATION_REQUIRED
        )
        return session.finish(
            outcome=outcome,
            previous=assessment,
            new=new_assessment,
            operation=self.operation,
            job_id=command.job_id,
            stages_attempted=(FinalizationStage.INVENTORY_RECONCILIATION,),
            stages_completed=(FinalizationStage.INVENTORY_RECONCILIATION,),
        )
