"""Verify and republish recovery use cases — Phase 3.4."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.application.ports.artifact_manifest_store import ArtifactManifestStore
from src.application.ports.clock import Clock
from src.application.ports.finalization_recovery_store import FinalizationRecoveryStore
from src.application.ports.finalization_stage_store import FinalizationStageStore
from src.application.ports.repositories import AisleRepository, InventoryRepository, JobRepository
from src.application.services.artifact_recovery_source_resolver import ArtifactRecoverySourceResolver
from src.application.services.finalization_assessment_service import FinalizationAssessmentService
from src.application.services.finalization_recovery_eligibility import FinalizationRecoveryEligibility
from src.application.services.finalization_recovery_support import RecoverySession, build_stage_recorder
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.services.job_artifact_verifier import JobArtifactVerifier
from src.application.services.job_domain_result_verifier import JobDomainResultVerifier
from src.application.services.operational_result_promotion_service import (
    OperationalResultPromotionService,
)
from src.application.use_cases.finalization_recovery.recovery_command import RecoveryCommand
from src.application.use_cases.finalization_recovery.recovery_helpers import (
    gate_or_dry_run,
    make_recovery_result,
    not_eligible,
)
from src.domain.jobs.artifact_policy import is_required_artifact_kind
from src.domain.jobs.finalization import LastCompletedFinalizationStep
from src.domain.jobs.finalization_evidence import (
    ArtifactVerificationVerdict,
    DomainSnapshotVerdict,
    EvidenceLevel,
    FinalizationStage,
    StageStatus,
)
from src.domain.jobs.finalization_recovery import (
    ArtifactRecoverySourceStatus,
    RecoveryOperation,
    RecoveryOutcome,
    RecoveryResult,
)
from src.infrastructure.pipeline.worker_durable_artifact_publisher import (
    DEFAULT_V3_WORKER_RUN_SEGMENT,
    merge_durable_into_result_json,
    republish_worker_durable_artifacts,
)
from src.infrastructure.storage.artifact_store import ArtifactStore


@dataclass
class FinalizationRecoveryDependencies:
    job_repo: JobRepository
    aisle_repo: AisleRepository
    inventory_repo: InventoryRepository
    stage_store: FinalizationStageStore
    manifest_store: ArtifactManifestStore
    recovery_store: FinalizationRecoveryStore
    assessment_service: FinalizationAssessmentService
    domain_verifier: JobDomainResultVerifier
    artifact_verifier: JobArtifactVerifier
    source_resolver: ArtifactRecoverySourceResolver
    promotion_service: OperationalResultPromotionService
    inventory_reconciler: InventoryStatusReconciler
    artifact_store: ArtifactStore | None
    clock: Clock
    eligibility: FinalizationRecoveryEligibility | None = None

    def recorder(self):
        return build_stage_recorder(
            job_repo=self.job_repo,
            stage_store=self.stage_store,
            manifest_store=self.manifest_store,
            clock=self.clock,
        )

    def session(self) -> RecoverySession:
        return RecoverySession(
            recovery_store=self.recovery_store,
            assessment_service=self.assessment_service,
            eligibility=self.eligibility or FinalizationRecoveryEligibility(),
            job_repo=self.job_repo,
            clock=self.clock,
        )


class VerifyJobFinalizationUseCase:
    operation = RecoveryOperation.VERIFY

    def __init__(self, deps: FinalizationRecoveryDependencies) -> None:
        self._deps = deps
        self._eligibility = deps.eligibility or FinalizationRecoveryEligibility()

    def execute(self, command: RecoveryCommand) -> RecoveryResult:
        assessment = self._deps.assessment_service.assess(command.job_id)
        job = self._deps.job_repo.get_by_id(command.job_id)
        if job is None:
            return not_eligible(command, assessment, self.operation, "job_not_found", self._deps)
        blocked = self._eligibility.refuse_global_assessment(assessment, self.operation)
        if blocked == "already_complete":
            return make_recovery_result(
                command, assessment, assessment, RecoveryOutcome.ALREADY_COMPLETE, self.operation, self._deps
            )
        if command.dry_run:
            return make_recovery_result(
                command,
                assessment,
                assessment,
                RecoveryOutcome.VERIFICATION_REQUIRED,
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
        if job.target_type == "aisle" and job.target_id:
            snap = self._deps.domain_verifier.verify(job_id=job.id, aisle_id=job.target_id)
            domain_stage = self._deps.stage_store.get_stage(job.id, FinalizationStage.DOMAIN_RESULTS)
            if domain_stage and domain_stage.status == StageStatus.VERIFICATION_REQUIRED:
                if snap.verdict in (
                    DomainSnapshotVerdict.CONFIRMED_COMPLETE,
                    DomainSnapshotVerdict.CONFIRMED_EMPTY_VALID,
                ):
                    self._deps.stage_store.transition_stage(
                        job_id=job.id,
                        stage=FinalizationStage.DOMAIN_RESULTS,
                        new_status=StageStatus.COMPLETED,
                        evidence_level=EvidenceLevel.CONFIRMED,
                        completed_at=domain_stage.completed_at or now,
                        verified_at=now,
                        verification_source="recovery_verify",
                        expected_version=domain_stage.version,
                        now=now,
                    )
                elif snap.verdict == DomainSnapshotVerdict.INCOMPLETE:
                    self._deps.stage_store.transition_stage(
                        job_id=job.id,
                        stage=FinalizationStage.DOMAIN_RESULTS,
                        new_status=StageStatus.FAILED,
                        evidence_level=EvidenceLevel.VERIFICATION_REQUIRED,
                        last_error_code="domain_snapshot_incomplete",
                        expected_version=domain_stage.version,
                        now=now,
                    )
        new_assessment = session.fresh_assessment(command.job_id)
        outcome = (
            RecoveryOutcome.RECOVERED
            if new_assessment.outcome != assessment.outcome
            else RecoveryOutcome.VERIFICATION_REQUIRED
        )
        return session.finish(
            outcome=outcome,
            previous=assessment,
            new=new_assessment,
            operation=self.operation,
            job_id=command.job_id,
            stages_attempted=(FinalizationStage.DOMAIN_RESULTS,),
        )


class RepublishJobArtifactsUseCase:
    operation = RecoveryOperation.REPUBLISH_ARTIFACTS

    def __init__(self, deps: FinalizationRecoveryDependencies) -> None:
        self._deps = deps
        self._eligibility = deps.eligibility or FinalizationRecoveryEligibility()

    def execute(self, command: RecoveryCommand) -> RecoveryResult:
        assessment = self._deps.assessment_service.assess(command.job_id)
        job = self._deps.job_repo.get_by_id(command.job_id)
        if job is None:
            return not_eligible(command, assessment, self.operation, "job_not_found", self._deps)
        gate = gate_or_dry_run(command, assessment, job, self.operation, self._eligibility, self._deps)
        if gate is not None:
            return gate
        if not self._eligibility.stage_precondition_met(
            assessment, FinalizationStage.DOMAIN_RESULTS
        ):
            return not_eligible(
                command, assessment, self.operation, "domain_results_not_completed", self._deps
            )
        checks = self._deps.artifact_verifier.verify_required(command.job_id)
        if all(c.verdict == ArtifactVerificationVerdict.CONFIRMED for c in checks):
            return make_recovery_result(
                command, assessment, assessment, RecoveryOutcome.ALREADY_COMPLETE, self.operation, self._deps
            )
        sources = self._deps.source_resolver.resolve_all(job)
        pending = [
            s
            for s in sources
            if self._deps.artifact_verifier.verify_entry(command.job_id, s.artifact_kind).verdict
            != ArtifactVerificationVerdict.CONFIRMED
        ]
        unavailable = [
            s
            for s in pending
            if s.status
            not in (
                ArtifactRecoverySourceStatus.AVAILABLE_EXACT,
                ArtifactRecoverySourceStatus.AVAILABLE_RECONSTRUCTED,
            )
        ]
        if unavailable:
            return make_recovery_result(
                command,
                assessment,
                assessment,
                RecoveryOutcome.SOURCE_UNAVAILABLE,
                self.operation,
                self._deps,
                error_code="artifact_source_unavailable",
                sanitized_message=unavailable[0].detail,
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
        kinds_to_publish: set[str] = set()
        source_paths: dict[str, Path] = {}
        for src in pending:
            kinds_to_publish.add(src.artifact_kind)
            if src.local_path:
                source_paths[src.artifact_kind] = Path(src.local_path)
        run_dir = Path(pending[0].run_dir) if pending and pending[0].run_dir else None
        if run_dir is None or self._deps.artifact_store is None:
            return session.finish(
                outcome=RecoveryOutcome.SOURCE_UNAVAILABLE,
                previous=assessment,
                new=assessment,
                operation=self.operation,
                job_id=command.job_id,
                error_code="artifact_store_unavailable",
            )
        published = republish_worker_durable_artifacts(
            self._deps.artifact_store,
            job_id=command.job_id,
            run_segment=DEFAULT_V3_WORKER_RUN_SEGMENT,
            run_dir=run_dir,
            kinds=frozenset(kinds_to_publish),
            source_paths=source_paths,
        )
        now = self._deps.clock.now()
        self._deps.manifest_store.ensure_expected_entries(command.job_id, now=now)
        recorder = self._deps.recorder()
        for kind, meta in published.items():
            self._deps.manifest_store.mark_published(
                job_id=command.job_id,
                artifact_kind=kind,
                storage_key=str(meta["storage_key"]),
                size_bytes=meta.get("file_size_bytes"),
                content_hash=meta.get("etag"),
                required=is_required_artifact_kind(kind),
                now=now,
            )
        if self._deps.manifest_store.required_kinds_published(command.job_id):
            recorder.mark_completed_for_step(
                command.job_id,
                LastCompletedFinalizationStep.ARTIFACTS_PUBLISHED,
                evidence_level=EvidenceLevel.CONFIRMED,
                verification_source="recovery_republish",
            )
        if job.result_json is not None:
            merge_durable_into_result_json(job.result_json, published)
            self._deps.job_repo.save(job)
        new_assessment = session.fresh_assessment(command.job_id)
        post_checks = self._deps.artifact_verifier.verify_required(command.job_id)
        outcome = (
            RecoveryOutcome.RECOVERED
            if all(c.verdict == ArtifactVerificationVerdict.CONFIRMED for c in post_checks)
            else RecoveryOutcome.VERIFICATION_REQUIRED
        )
        return session.finish(
            outcome=outcome,
            previous=assessment,
            new=new_assessment,
            operation=self.operation,
            job_id=command.job_id,
            stages_attempted=(FinalizationStage.REQUIRED_ARTIFACTS,),
            stages_completed=(FinalizationStage.REQUIRED_ARTIFACTS,),
        )
