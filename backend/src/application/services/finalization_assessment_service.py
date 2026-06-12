"""Read-only finalization assessment — Phase 3.3."""

from __future__ import annotations

from src.application.ports.artifact_manifest_store import ArtifactManifestStore
from src.application.ports.finalization_stage_store import FinalizationStageStore
from src.application.ports.repositories import AisleRepository, JobRepository
from src.application.services.job_artifact_verifier import JobArtifactVerifier
from src.application.services.job_domain_result_verifier import JobDomainResultVerifier
from src.domain.jobs.entities import JobStatus
from src.domain.jobs.finalization_evidence import (
    FINALIZATION_STAGE_ORDER,
    DomainSnapshotVerdict,
    EvidenceLevel,
    FinalizationAssessment,
    FinalizationAssessmentOutcome,
    FinalizationStage,
    StageAssessment,
    StageStatus,
)


class FinalizationAssessmentService:
    """Normalize authoritative stage evidence into a recovery-oriented view (read-only)."""

    def __init__(
        self,
        *,
        job_repo: JobRepository,
        aisle_repo: AisleRepository,
        stage_store: FinalizationStageStore,
        manifest_store: ArtifactManifestStore,
        domain_verifier: JobDomainResultVerifier,
        artifact_verifier: JobArtifactVerifier,
    ) -> None:
        self._job_repo = job_repo
        self._aisle_repo = aisle_repo
        self._stage_store = stage_store
        self._manifest_store = manifest_store
        self._domain_verifier = domain_verifier
        self._artifact_verifier = artifact_verifier

    def assess(self, job_id: str) -> FinalizationAssessment:
        job = self._job_repo.get_by_id(job_id)
        aisle_id = job.target_id if job and job.target_type == "aisle" else None
        stages_map = {s.stage: s for s in self._stage_store.list_stages(job_id)}
        stage_views: dict[str, StageAssessment] = {}
        last_confirmed: FinalizationStage | None = None
        next_required: FinalizationStage | None = None

        for stage in FINALIZATION_STAGE_ORDER:
            rec = stages_map.get(stage)
            if rec is None:
                status = StageStatus.UNKNOWN
                level = EvidenceLevel.UNKNOWN
                completed_at = None
                verification_required = stage == FinalizationStage.DOMAIN_RESULTS
            else:
                status = rec.status
                level = rec.evidence_level
                completed_at = rec.completed_at
                verification_required = (
                    status == StageStatus.VERIFICATION_REQUIRED
                    or level == EvidenceLevel.VERIFICATION_REQUIRED
                )
            stage_views[stage.value] = StageAssessment(
                stage=stage,
                status=status,
                evidence_level=level,
                completed_at=completed_at,
                verification_required=verification_required,
                last_error_code=rec.last_error_code if rec else None,
            )
            if rec and rec.status == StageStatus.COMPLETED:
                last_confirmed = stage
            elif next_required is None and (
                rec is None or rec.status not in (StageStatus.COMPLETED,)
            ):
                next_required = stage

        outcome = self._derive_outcome(
            job_id=job_id,
            aisle_id=aisle_id,
            job_status=job.status if job else None,
            stages_map=stages_map,
            last_confirmed=last_confirmed,
        )
        technical = self._technical_status(job, stages_map, aisle_id)
        finalization_status = (
            job.finalization_status.value
            if job and hasattr(job.finalization_status, "value")
            else "unknown"
        )
        blocking = None if outcome == FinalizationAssessmentOutcome.COMPLETE else outcome.value
        recovery = outcome not in (
            FinalizationAssessmentOutcome.COMPLETE,
            FinalizationAssessmentOutcome.FAILED_BEFORE_DOMAIN_COMMIT,
        )
        return FinalizationAssessment(
            job_id=job_id,
            outcome=outcome,
            technical_result_status=technical,
            finalization_status=finalization_status,
            last_confirmed_stage=last_confirmed,
            next_required_stage=next_required,
            recovery_candidate=recovery,
            blocking_reason=blocking,
            stages=stage_views,
        )

    def assert_operational_pointer_invariant(self, aisle_id: str) -> bool:
        aisle = self._aisle_repo.get_by_id(aisle_id)
        if aisle is None or not aisle.operational_job_id:
            return True
        op_job = self._job_repo.get_by_id(aisle.operational_job_id)
        return op_job is not None and op_job.status == JobStatus.SUCCEEDED

    def _technical_status(
        self,
        job,
        stages_map: dict,
        aisle_id: str | None,
    ) -> str:
        if job is None:
            return "unknown"
        if job.status == JobStatus.SUCCEEDED:
            return "confirmed"
        domain = stages_map.get(FinalizationStage.DOMAIN_RESULTS)
        if domain and domain.status == StageStatus.COMPLETED:
            if aisle_id:
                snap = self._domain_verifier.verify(job_id=job.id, aisle_id=aisle_id)
                if snap.verdict in (
                    DomainSnapshotVerdict.CONFIRMED_COMPLETE,
                    DomainSnapshotVerdict.CONFIRMED_EMPTY_VALID,
                ):
                    return "confirmed"
            return "verification_required"
        return "not_confirmed"

    def _derive_outcome(
        self,
        *,
        job_id: str,
        aisle_id: str | None,
        job_status: JobStatus | None,
        stages_map: dict,
        last_confirmed: FinalizationStage | None,
    ) -> FinalizationAssessmentOutcome:
        if job_status in (JobStatus.FAILED, JobStatus.CANCELED):
            domain = stages_map.get(FinalizationStage.DOMAIN_RESULTS)
            if domain is None or domain.status != StageStatus.COMPLETED:
                return FinalizationAssessmentOutcome.FAILED_BEFORE_DOMAIN_COMMIT

        domain = stages_map.get(FinalizationStage.DOMAIN_RESULTS)
        if domain is None or domain.status != StageStatus.COMPLETED:
            if aisle_id:
                snap = self._domain_verifier.verify(job_id=job_id, aisle_id=aisle_id)
                if snap.verdict in (
                    DomainSnapshotVerdict.CONFIRMED_COMPLETE,
                    DomainSnapshotVerdict.CONFIRMED_EMPTY_VALID,
                ):
                    return FinalizationAssessmentOutcome.VERIFICATION_REQUIRED
            return FinalizationAssessmentOutcome.FAILED_BEFORE_DOMAIN_COMMIT

        artifacts = stages_map.get(FinalizationStage.REQUIRED_ARTIFACTS)
        if artifacts is None or artifacts.status != StageStatus.COMPLETED:
            if self._manifest_store.any_required_failed(job_id):
                return FinalizationAssessmentOutcome.DOMAIN_COMMITTED_ARTIFACTS_MISSING
            if not self._manifest_store.required_kinds_published(job_id):
                return FinalizationAssessmentOutcome.DOMAIN_COMMITTED_ARTIFACTS_MISSING
            return FinalizationAssessmentOutcome.VERIFICATION_REQUIRED

        terminal = stages_map.get(FinalizationStage.JOB_TERMINALIZATION)
        if job_status == JobStatus.SUCCEEDED and (
            terminal is None or terminal.status != StageStatus.COMPLETED
        ):
            return FinalizationAssessmentOutcome.ARTIFACTS_COMPLETE_TERMINALIZATION_MISSING

        inv = stages_map.get(FinalizationStage.INVENTORY_RECONCILIATION)
        if job_status == JobStatus.SUCCEEDED and (
            inv is None or inv.status != StageStatus.COMPLETED
        ):
            return FinalizationAssessmentOutcome.TECHNICALLY_SUCCEEDED_RECONCILIATION_PENDING

        if inv and inv.status == StageStatus.COMPLETED:
            return FinalizationAssessmentOutcome.COMPLETE

        if job_status == JobStatus.SUCCEEDED:
            return FinalizationAssessmentOutcome.TECHNICALLY_SUCCEEDED_RECONCILIATION_PENDING

        return FinalizationAssessmentOutcome.VERIFICATION_REQUIRED
