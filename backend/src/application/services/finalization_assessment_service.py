"""Read-only finalization assessment — Phase 3.3."""

from __future__ import annotations

from src.application.ports.artifact_manifest_store import ArtifactManifestStore
from src.application.ports.finalization_stage_store import FinalizationStageStore
from src.application.ports.repositories import AisleRepository, JobRepository
from src.application.services.job_artifact_verifier import JobArtifactVerifier
from src.application.services.job_domain_result_verifier import JobDomainResultVerifier
from src.domain.jobs.entities import Job, JobStatus
from src.domain.jobs.finalization_evidence import (
    FINALIZATION_STAGE_ORDER,
    ArtifactVerificationVerdict,
    DomainSnapshotVerdict,
    EvidenceLevel,
    FinalizationAssessment,
    FinalizationAssessmentOutcome,
    FinalizationStage,
    FinalizationStageRecord,
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
        stages_list = list(self._stage_store.list_stages(job_id))
        stages_map = {s.stage: s for s in stages_list}
        manifest_entries = list(self._manifest_store.list_entries(job_id))

        if job is None:
            blocking = (
                "orphan_finalization_evidence"
                if stages_list or manifest_entries
                else "job_not_found"
            )
            return FinalizationAssessment(
                job_id=job_id,
                outcome=FinalizationAssessmentOutcome.INCONSISTENT,
                technical_result_status="unknown",
                finalization_status="unknown",
                last_confirmed_stage=None,
                next_required_stage=FinalizationStage.DOMAIN_RESULTS,
                recovery_candidate=False,
                blocking_reason=blocking,
                stages=self._unknown_stage_views(stages_map),
            )

        aisle_id = job.target_id if job.target_type == "aisle" else None
        stage_views = self._build_stage_views(stages_map)
        last_confirmed, next_required = self._progress_pointers(stages_map)

        inconsistency = self._detect_inconsistency(job, stages_map, aisle_id)
        if inconsistency is not None:
            return self._result(
                job=job,
                stages_map=stages_map,
                outcome=FinalizationAssessmentOutcome.INCONSISTENT,
                last_confirmed=last_confirmed,
                next_required=next_required,
                stage_views=stage_views,
                blocking_reason=inconsistency,
            )

        if job.status in (JobStatus.FAILED, JobStatus.CANCELED):
            domain = stages_map.get(FinalizationStage.DOMAIN_RESULTS)
            if domain is None or domain.status != StageStatus.COMPLETED:
                return self._result(
                    job=job,
                    stages_map=stages_map,
                    outcome=FinalizationAssessmentOutcome.FAILED_BEFORE_DOMAIN_COMMIT,
                    last_confirmed=last_confirmed,
                    next_required=FinalizationStage.DOMAIN_RESULTS,
                    stage_views=stage_views,
                    recovery=False,
                )

        domain = stages_map.get(FinalizationStage.DOMAIN_RESULTS)
        if domain is None or domain.status != StageStatus.COMPLETED:
            if aisle_id:
                snap = self._domain_verifier.verify(job_id=job_id, aisle_id=aisle_id)
                if snap.verdict in (
                    DomainSnapshotVerdict.CONFIRMED_COMPLETE,
                    DomainSnapshotVerdict.CONFIRMED_EMPTY_VALID,
                ):
                    return self._result(
                        job=job,
                        stages_map=stages_map,
                        outcome=FinalizationAssessmentOutcome.VERIFICATION_REQUIRED,
                        last_confirmed=last_confirmed,
                        next_required=FinalizationStage.DOMAIN_RESULTS,
                        stage_views=stage_views,
                    )
            return self._result(
                job=job,
                stages_map=stages_map,
                outcome=FinalizationAssessmentOutcome.FAILED_BEFORE_DOMAIN_COMMIT,
                last_confirmed=last_confirmed,
                next_required=FinalizationStage.DOMAIN_RESULTS,
                stage_views=stage_views,
                recovery=False,
            )

        artifact_outcome = self._assess_required_artifacts(job_id, stages_map)
        if artifact_outcome is not None:
            return self._result(
                job=job,
                stages_map=stages_map,
                outcome=artifact_outcome,
                last_confirmed=last_confirmed,
                next_required=next_required,
                stage_views=stage_views,
            )

        if self._is_strict_complete(job_id, job, stages_map, aisle_id):
            return self._result(
                job=job,
                stages_map=stages_map,
                outcome=FinalizationAssessmentOutcome.COMPLETE,
                last_confirmed=FinalizationStage.INVENTORY_RECONCILIATION,
                next_required=None,
                stage_views=stage_views,
                recovery=False,
            )

        if job.status == JobStatus.SUCCEEDED:
            terminal = stages_map.get(FinalizationStage.JOB_TERMINALIZATION)
            if terminal is None or terminal.status != StageStatus.COMPLETED:
                return self._result(
                    job=job,
                    stages_map=stages_map,
                    outcome=FinalizationAssessmentOutcome.ARTIFACTS_COMPLETE_TERMINALIZATION_MISSING,
                    last_confirmed=last_confirmed,
                    next_required=FinalizationStage.JOB_TERMINALIZATION,
                    stage_views=stage_views,
                )
            return self._result(
                job=job,
                stages_map=stages_map,
                outcome=FinalizationAssessmentOutcome.TECHNICALLY_SUCCEEDED_RECONCILIATION_PENDING,
                last_confirmed=last_confirmed,
                next_required=next_required,
                stage_views=stage_views,
            )

        return self._result(
            job=job,
            stages_map=stages_map,
            outcome=FinalizationAssessmentOutcome.VERIFICATION_REQUIRED,
            last_confirmed=last_confirmed,
            next_required=next_required,
            stage_views=stage_views,
        )

    def assert_operational_pointer_invariant(self, aisle_id: str) -> bool:
        aisle = self._aisle_repo.get_by_id(aisle_id)
        if aisle is None or not aisle.operational_job_id:
            return True
        op_job = self._job_repo.get_by_id(aisle.operational_job_id)
        return op_job is not None and op_job.status == JobStatus.SUCCEEDED

    def _assess_required_artifacts(
        self, job_id: str, stages_map: dict[FinalizationStage, FinalizationStageRecord]
    ) -> FinalizationAssessmentOutcome | None:
        checks = self._artifact_verifier.verify_required(job_id)
        for check in checks:
            if check.verdict == ArtifactVerificationVerdict.MISMATCH:
                return FinalizationAssessmentOutcome.INCONSISTENT
            if check.verdict == ArtifactVerificationVerdict.MISSING:
                return FinalizationAssessmentOutcome.DOMAIN_COMMITTED_ARTIFACTS_MISSING
            if check.verdict != ArtifactVerificationVerdict.CONFIRMED:
                return FinalizationAssessmentOutcome.VERIFICATION_REQUIRED

        artifacts_stage = stages_map.get(FinalizationStage.REQUIRED_ARTIFACTS)
        if artifacts_stage is None or artifacts_stage.status != StageStatus.COMPLETED:
            if self._manifest_store.any_required_failed(job_id):
                return FinalizationAssessmentOutcome.DOMAIN_COMMITTED_ARTIFACTS_MISSING
            if self._manifest_store.missing_required_kinds(job_id):
                return FinalizationAssessmentOutcome.DOMAIN_COMMITTED_ARTIFACTS_MISSING
            return FinalizationAssessmentOutcome.VERIFICATION_REQUIRED
        return None

    def _is_strict_complete(
        self,
        job_id: str,
        job: Job,
        stages_map: dict[FinalizationStage, FinalizationStageRecord],
        aisle_id: str | None,
    ) -> bool:
        if job.status != JobStatus.SUCCEEDED:
            return False
        for stage in FINALIZATION_STAGE_ORDER:
            rec = stages_map.get(stage)
            if rec is None or rec.status != StageStatus.COMPLETED or rec.completed_at is None:
                return False
        checks = self._artifact_verifier.verify_required(job_id)
        if not all(c.verdict == ArtifactVerificationVerdict.CONFIRMED for c in checks):
            return False
        if aisle_id and not self.assert_operational_pointer_invariant(aisle_id):
            return False
        if aisle_id:
            snap = self._domain_verifier.verify(job_id=job_id, aisle_id=aisle_id)
            if snap.verdict not in (
                DomainSnapshotVerdict.CONFIRMED_COMPLETE,
                DomainSnapshotVerdict.CONFIRMED_EMPTY_VALID,
            ):
                return False
        return True

    def _detect_inconsistency(
        self,
        job: Job,
        stages_map: dict[FinalizationStage, FinalizationStageRecord],
        aisle_id: str | None,
    ) -> str | None:
        max_completed_idx = -1
        for idx, stage in enumerate(FINALIZATION_STAGE_ORDER):
            rec = stages_map.get(stage)
            if rec and rec.status == StageStatus.COMPLETED:
                max_completed_idx = idx

        for idx in range(max_completed_idx + 1):
            rec = stages_map.get(FINALIZATION_STAGE_ORDER[idx])
            if rec is None or rec.status != StageStatus.COMPLETED or rec.completed_at is None:
                return "stage_order_gap"

        if aisle_id and not self.assert_operational_pointer_invariant(aisle_id):
            return "operational_pointer_invalid"

        for check in self._artifact_verifier.verify_required(job.id):
            if check.verdict == ArtifactVerificationVerdict.MISMATCH:
                return "artifact_storage_mismatch"
            entry = self._manifest_store.get_entry(job.id, check.artifact_kind)
            if entry and entry.status.value == "published" and not entry.storage_key:
                return "artifact_manifest_missing_storage_key"

        return None

    def _technical_status(
        self,
        job: Job,
        stages_map: dict[FinalizationStage, FinalizationStageRecord],
        aisle_id: str | None,
    ) -> str:
        if job.status == JobStatus.SUCCEEDED:
            return "confirmed"
        domain = stages_map.get(FinalizationStage.DOMAIN_RESULTS)
        if domain and domain.status == StageStatus.COMPLETED and aisle_id:
            snap = self._domain_verifier.verify(job_id=job.id, aisle_id=aisle_id)
            if snap.verdict in (
                DomainSnapshotVerdict.CONFIRMED_COMPLETE,
                DomainSnapshotVerdict.CONFIRMED_EMPTY_VALID,
            ):
                return "confirmed"
            return "verification_required"
        return "not_confirmed"

    def _build_stage_views(
        self, stages_map: dict[FinalizationStage, FinalizationStageRecord]
    ) -> dict[str, StageAssessment]:
        views: dict[str, StageAssessment] = {}
        for stage in FINALIZATION_STAGE_ORDER:
            rec = stages_map.get(stage)
            if rec is None:
                views[stage.value] = StageAssessment(
                    stage=stage,
                    status=StageStatus.UNKNOWN,
                    evidence_level=EvidenceLevel.UNKNOWN,
                    completed_at=None,
                    verification_required=True,
                    last_error_code=None,
                )
            else:
                views[stage.value] = StageAssessment(
                    stage=stage,
                    status=rec.status,
                    evidence_level=rec.evidence_level,
                    completed_at=rec.completed_at,
                    verification_required=(
                        rec.status == StageStatus.VERIFICATION_REQUIRED
                        or rec.evidence_level == EvidenceLevel.VERIFICATION_REQUIRED
                    ),
                    last_error_code=rec.last_error_code,
                )
        return views

    def _unknown_stage_views(
        self, stages_map: dict[FinalizationStage, FinalizationStageRecord]
    ) -> dict[str, StageAssessment]:
        if not stages_map:
            return self._build_stage_views({})
        return self._build_stage_views(stages_map)

    def _progress_pointers(
        self, stages_map: dict[FinalizationStage, FinalizationStageRecord]
    ) -> tuple[FinalizationStage | None, FinalizationStage | None]:
        last_confirmed: FinalizationStage | None = None
        next_required: FinalizationStage | None = None
        for stage in FINALIZATION_STAGE_ORDER:
            rec = stages_map.get(stage)
            if rec and rec.status == StageStatus.COMPLETED:
                last_confirmed = stage
            elif next_required is None and (rec is None or rec.status != StageStatus.COMPLETED):
                next_required = stage
        return last_confirmed, next_required

    def _result(
        self,
        *,
        job: Job,
        stages_map: dict[FinalizationStage, FinalizationStageRecord],
        outcome: FinalizationAssessmentOutcome,
        last_confirmed: FinalizationStage | None,
        next_required: FinalizationStage | None,
        stage_views: dict[str, StageAssessment],
        recovery: bool = True,
        blocking_reason: str | None = None,
    ) -> FinalizationAssessment:
        blocking = blocking_reason if blocking_reason is not None else (
            None if outcome == FinalizationAssessmentOutcome.COMPLETE else outcome.value
        )
        recovery_candidate = recovery and outcome not in (
            FinalizationAssessmentOutcome.COMPLETE,
            FinalizationAssessmentOutcome.FAILED_BEFORE_DOMAIN_COMMIT,
        )
        aisle_id = job.target_id if job.target_type == "aisle" else None
        return FinalizationAssessment(
            job_id=job.id,
            outcome=outcome,
            technical_result_status=self._technical_status(job, stages_map, aisle_id),
            finalization_status=job.finalization_status.value,
            last_confirmed_stage=last_confirmed,
            next_required_stage=next_required,
            recovery_candidate=recovery_candidate,
            blocking_reason=blocking,
            stages=stage_views,
        )
