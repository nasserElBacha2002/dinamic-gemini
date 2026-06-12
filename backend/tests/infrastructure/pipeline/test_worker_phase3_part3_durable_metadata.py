"""Phase 3.3 — durable finalization metadata (stage evidence, assessment, verification)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.domain.jobs.finalization import FinalizationStatus, LastCompletedFinalizationStep
from src.domain.jobs.finalization_evidence import (
    DomainSnapshotVerdict,
    EvidenceLevel,
    FinalizationAssessment,
    FinalizationAssessmentOutcome,
    FinalizationStage,
    StageAssessment,
    StageStatus,
)
from src.infrastructure.pipeline.job_finalization_tracker import sanitize_finalization_error_metadata
from src.application.services.default_job_scoped_recompute_factory import (
    DefaultJobScopedRecomputeFactory,
)
from src.application.services.finalization_assessment_service import FinalizationAssessmentService
from src.application.services.finalization_projection_service import FinalizationProjectionService
from src.application.services.finalization_stage_transitions import (
    InvalidStageTransitionError,
    assert_stage_transition_allowed,
)
from src.application.services.job_artifact_verifier import JobArtifactVerifier
from src.application.services.job_domain_result_verifier import JobDomainResultVerifier
from src.application.use_cases.pipeline.persist_aisle_result import (
    PersistAisleResultCommand,
    PersistAisleResultUseCase,
)
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.persistence.memory_finalization_stage_store import (
    MemoryFinalizationStageStore,
)
from src.infrastructure.persistence.memory_job_result_unit_of_work import (
    MemoryJobResultUnitOfWorkFactory,
)
from src.infrastructure.pipeline.hybrid_report_to_domain_adapter import (
    default_map_hybrid_report_to_domain,
)
from src.domain.jobs.artifact_policy import (
    ARTIFACT_KIND_EXECUTION_LOG,
    ARTIFACT_KIND_HYBRID_REPORT_CSV,
    ARTIFACT_KIND_HYBRID_REPORT_JSON,
    REQUIRED_ARTIFACT_KINDS,
)
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_evidence_repository import MemoryEvidenceRepository
from src.infrastructure.repositories.memory_final_count_repository import MemoryFinalCountRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
from src.infrastructure.repositories.memory_normalized_label_repository import (
    MemoryNormalizedLabelRepository,
)
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_product_record_repository import (
    MemoryProductRecordRepository,
)
from src.infrastructure.persistence.memory_artifact_manifest_store import MemoryArtifactManifestStore
from src.infrastructure.repositories.memory_raw_label_repository import MemoryRawLabelRepository
from tests.support.worker_phase1.doubles import ArtifactUploadSpy
from tests.support.worker_phase1.executor_harness import (
    ExecutorHarness,
    FixedClock,
    make_entity_hybrid_report,
)
from tests.support.worker_phase2.recompute_doubles import FailingJobScopedRecomputeFactory


def _cas_transition(store, *, job_id: str, stage: FinalizationStage, now: datetime, **kwargs):
    """Transition with optimistic concurrency using the current row version."""
    existing = store.get_stage(job_id, stage)
    return store.transition_stage(
        job_id=job_id,
        stage=stage,
        expected_version=existing.version if existing else None,
        now=now,
        **kwargs,
    )


def _build_assessment_service(
    harness: ExecutorHarness,
) -> FinalizationAssessmentService:
    return FinalizationAssessmentService(
        job_repo=harness.job_repo,
        aisle_repo=harness.aisle_repo,
        stage_store=harness.stage_store,
        manifest_store=harness.manifest_store,
        domain_verifier=JobDomainResultVerifier(
            aisle_repo=harness.aisle_repo,
            position_repo=harness.position_repo,
            product_repo=harness.product_repo,
            evidence_repo=harness.evidence_repo,
            raw_label_repo=harness.raw_repo,
            normalized_label_repo=harness.norm_repo,
            final_count_repo=harness.final_repo,
            stage_store=harness.stage_store,
        ),
        artifact_verifier=JobArtifactVerifier(
            manifest_store=harness.manifest_store,
            artifact_store=harness.artifact_store,
        ),
    )


def _persist_use_case(harness: ExecutorHarness, **overrides) -> PersistAisleResultUseCase:
    stage_store = overrides.pop("stage_store", harness.stage_store)
    return PersistAisleResultUseCase(
        position_repo=harness.position_repo,
        product_record_repo=harness.product_repo,
        evidence_repo=harness.evidence_repo,
        clock=FixedClock(harness.now),
        hybrid_mapper=default_map_hybrid_report_to_domain,
        aisle_repo=harness.aisle_repo,
        raw_label_repo=harness.raw_repo,
        normalized_label_repo=harness.norm_repo,
        final_count_repo=harness.final_repo,
        job_scoped_recompute_factory=overrides.pop(
            "job_scoped_recompute_factory", DefaultJobScopedRecomputeFactory()
        ),
        job_result_uow_factory=MemoryJobResultUnitOfWorkFactory(stage_store=stage_store),
    )


def test_p3_3_t01_transactional_domain_evidence_commits_with_rows(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_id="job-tx")
    run_dir = harness.seed_run_dir()
    uc = _persist_use_case(harness)
    cmd = PersistAisleResultCommand(
        aisle_id=harness.aisle_id,
        job_id=harness.job_id,
        report=make_entity_hybrid_report([]),
        run_dir=run_dir,
    )
    uc.execute(cmd)
    stage = harness.stage_store.get_stage(harness.job_id, FinalizationStage.DOMAIN_RESULTS)
    assert stage is not None
    assert stage.status == StageStatus.COMPLETED
    assert stage.evidence_level == EvidenceLevel.TRANSACTIONAL
    assert len(harness.positions_for_job()) == 0


def test_p3_3_t01_transactional_domain_evidence_rolls_back_on_recompute_failure(
    tmp_path,
) -> None:
    harness = ExecutorHarness.build(tmp_path, job_id="job-rb")
    run_dir = harness.seed_run_dir()
    uc = _persist_use_case(
        harness,
        job_scoped_recompute_factory=FailingJobScopedRecomputeFactory(),
    )
    with pytest.raises(RuntimeError):
        uc.execute(
            PersistAisleResultCommand(
                aisle_id=harness.aisle_id,
                job_id=harness.job_id,
                report=make_entity_hybrid_report([]),
                run_dir=run_dir,
            )
        )
    assert harness.stage_store.get_stage(harness.job_id, FinalizationStage.DOMAIN_RESULTS) is None
    assert len(harness.positions_for_job()) == 0


def test_p3_3_t02_crash_window_authoritative_domain_summary_stale(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_id="job-crash")
    run_dir = harness.seed_run_dir()
    _persist_use_case(harness).execute(
        PersistAisleResultCommand(
            aisle_id=harness.aisle_id,
            job_id=harness.job_id,
            report=make_entity_hybrid_report([]),
            run_dir=run_dir,
        )
    )
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    job.last_completed_finalization_step = LastCompletedFinalizationStep.NONE
    job.domain_persisted_at = None
    harness.job_repo.save(job)

    assessment = _build_assessment_service(harness).assess(harness.job_id)
    domain = assessment.stages[FinalizationStage.DOMAIN_RESULTS.value]
    assert domain.status == StageStatus.COMPLETED
    assert domain.evidence_level == EvidenceLevel.TRANSACTIONAL
    assert assessment.outcome in (
        FinalizationAssessmentOutcome.VERIFICATION_REQUIRED,
        FinalizationAssessmentOutcome.DOMAIN_COMMITTED_ARTIFACTS_MISSING,
    )


def test_p3_3_t03_valid_empty_domain_snapshot(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_id="job-empty")
    run_dir = harness.seed_run_dir(report=make_entity_hybrid_report([]))
    _persist_use_case(harness).execute(
        PersistAisleResultCommand(
            aisle_id=harness.aisle_id,
            job_id=harness.job_id,
            report=make_entity_hybrid_report([]),
            run_dir=run_dir,
        )
    )
    verifier = JobDomainResultVerifier(
        aisle_repo=harness.aisle_repo,
        position_repo=harness.position_repo,
        product_repo=harness.product_repo,
        evidence_repo=harness.evidence_repo,
        raw_label_repo=harness.raw_repo,
        normalized_label_repo=harness.norm_repo,
        final_count_repo=harness.final_repo,
        stage_store=harness.stage_store,
    )
    snap = verifier.verify(job_id=harness.job_id, aisle_id=harness.aisle_id)
    assert snap.verdict == DomainSnapshotVerdict.CONFIRMED_EMPTY_VALID
    stage = harness.stage_store.get_stage(harness.job_id, FinalizationStage.DOMAIN_RESULTS)
    assert stage is not None and stage.status == StageStatus.COMPLETED


def test_p3_3_t04_incomplete_domain_scope(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_id="job-inc")
    now = harness.now
    from src.domain.positions.entities import Position, PositionStatus

    harness.position_repo.save(
        Position(
            id="pos-1",
            aisle_id=harness.aisle_id,
            job_id=harness.job_id,
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=now,
            updated_at=now,
        )
    )
    verifier = JobDomainResultVerifier(
        aisle_repo=harness.aisle_repo,
        position_repo=harness.position_repo,
        product_repo=harness.product_repo,
        evidence_repo=harness.evidence_repo,
        raw_label_repo=harness.raw_repo,
        normalized_label_repo=harness.norm_repo,
        final_count_repo=harness.final_repo,
    )
    snap = verifier.verify(job_id=harness.job_id, aisle_id=harness.aisle_id)
    assert snap.verdict == DomainSnapshotVerdict.INCOMPLETE
    stage = harness.stage_store.get_stage(harness.job_id, FinalizationStage.DOMAIN_RESULTS)
    assert stage is None or stage.status != StageStatus.COMPLETED


def test_p3_3_t05_full_artifact_manifest_on_success(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    executor = harness.make_executor()
    handled = harness.run_with_mock_pipeline(executor)
    assert handled is True
    entries = {e.artifact_kind: e for e in harness.manifest_store.list_entries(harness.job_id)}
    assert entries[ARTIFACT_KIND_EXECUTION_LOG].required is True
    assert entries[ARTIFACT_KIND_HYBRID_REPORT_JSON].required is True
    assert entries[ARTIFACT_KIND_HYBRID_REPORT_CSV].required is False
    stage = harness.stage_store.get_stage(harness.job_id, FinalizationStage.REQUIRED_ARTIFACTS)
    assert stage is not None and stage.status == StageStatus.COMPLETED


def test_p3_3_t06_partial_artifact_publication_visible(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path)
    now = harness.now
    harness.manifest_store.mark_published(
        job_id=harness.job_id,
        artifact_kind=ARTIFACT_KIND_EXECUTION_LOG,
        storage_key="logs/exec.jsonl",
        size_bytes=10,
        content_hash=None,
        required=True,
        now=now,
    )
    harness.manifest_store.mark_failed(
        job_id=harness.job_id,
        artifact_kind=ARTIFACT_KIND_HYBRID_REPORT_JSON,
        required=True,
        error="upload failed",
        now=now,
    )
    _cas_transition(
        harness.stage_store,
        job_id=harness.job_id,
        stage=FinalizationStage.REQUIRED_ARTIFACTS,
        new_status=StageStatus.IN_PROGRESS,
        evidence_level=EvidenceLevel.CONFIRMED,
        now=now,
    )
    _cas_transition(
        harness.stage_store,
        job_id=harness.job_id,
        stage=FinalizationStage.REQUIRED_ARTIFACTS,
        new_status=StageStatus.FAILED,
        evidence_level=EvidenceLevel.CONFIRMED,
        last_error_code="ARTIFACT_PUBLISH_FAILED",
        now=now,
    )
    assert not harness.manifest_store.required_kinds_published(harness.job_id)
    stage = harness.stage_store.get_stage(harness.job_id, FinalizationStage.REQUIRED_ARTIFACTS)
    assert stage is not None and stage.status == StageStatus.FAILED


def test_p3_3_t07_artifact_storage_missing_reports_inconsistent(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path)
    now = harness.now
    harness.manifest_store.mark_published(
        job_id=harness.job_id,
        artifact_kind=ARTIFACT_KIND_EXECUTION_LOG,
        storage_key="missing/key.jsonl",
        size_bytes=5,
        content_hash=None,
        required=True,
        now=now,
    )

    class _MissingStore:
        def object_exists(self, key: str) -> bool:
            return False

        def object_size_bytes(self, key: str, *, bucket=None) -> int:
            return 0

    verifier = JobArtifactVerifier(
        manifest_store=harness.manifest_store,
        artifact_store=_MissingStore(),
    )
    result = verifier.verify_entry(harness.job_id, ARTIFACT_KIND_EXECUTION_LOG)
    assert result.verdict.value == "missing"
    assert harness.manifest_store.get_entry(harness.job_id, ARTIFACT_KIND_EXECUTION_LOG)


def test_p3_3_t08_technical_terminalization_verification_required(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_status=JobStatus.SUCCEEDED)
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    job.status = JobStatus.SUCCEEDED
    harness.job_repo.save(job)
    assessment = _build_assessment_service(harness).assess(harness.job_id)
    assert assessment.outcome in (
        FinalizationAssessmentOutcome.VERIFICATION_REQUIRED,
        FinalizationAssessmentOutcome.FAILED_BEFORE_DOMAIN_COMMIT,
        FinalizationAssessmentOutcome.ARTIFACTS_COMPLETE_TERMINALIZATION_MISSING,
    )


def test_p3_3_t09_operational_pointer_invariant_detection(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path)
    aisle = harness.aisle_repo.get_by_id(harness.aisle_id)
    assert aisle is not None
    bad_job = Job(
        id="bad-op-job",
        target_type="aisle",
        target_id=harness.aisle_id,
        job_type="process_aisle",
        status=JobStatus.FAILED,
        payload_json={"aisle_id": harness.aisle_id},
        created_at=harness.now,
        updated_at=harness.now,
    )
    harness.job_repo.save(bad_job)
    aisle.operational_job_id = bad_job.id
    harness.aisle_repo.save(aisle)
    svc = _build_assessment_service(harness)
    assert svc.assert_operational_pointer_invariant(harness.aisle_id) is False


def test_p3_3_t10_reconciliation_stage_separation(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_status=JobStatus.SUCCEEDED, artifact_store=ArtifactUploadSpy())
    now = harness.now
    for kind in REQUIRED_ARTIFACT_KINDS:
        storage_key = f"artifacts/{kind}"
        harness.artifact_store.uploaded_sizes[storage_key] = 10
        harness.manifest_store.mark_published(
            job_id=harness.job_id,
            artifact_kind=kind,
            storage_key=storage_key,
            size_bytes=10,
            content_hash=None,
            required=True,
            now=now,
        )
    for stage in (
        FinalizationStage.DOMAIN_RESULTS,
        FinalizationStage.REQUIRED_ARTIFACTS,
        FinalizationStage.JOB_TERMINALIZATION,
        FinalizationStage.OPERATIONAL_PROMOTION,
        FinalizationStage.AISLE_RECONCILIATION,
    ):
        _cas_transition(
            harness.stage_store,
            job_id=harness.job_id,
            stage=stage,
            new_status=StageStatus.COMPLETED,
            evidence_level=EvidenceLevel.CONFIRMED,
            completed_at=now,
            now=now,
        )
    _cas_transition(
        harness.stage_store,
        job_id=harness.job_id,
        stage=FinalizationStage.INVENTORY_RECONCILIATION,
        new_status=StageStatus.IN_PROGRESS,
        evidence_level=EvidenceLevel.CONFIRMED,
        now=now,
    )
    _cas_transition(
        harness.stage_store,
        job_id=harness.job_id,
        stage=FinalizationStage.INVENTORY_RECONCILIATION,
        new_status=StageStatus.FAILED,
        evidence_level=EvidenceLevel.CONFIRMED,
        last_error_code="INVENTORY_RECONCILIATION_FAILED",
        now=now,
    )
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    job.status = JobStatus.SUCCEEDED
    harness.job_repo.save(job)
    assessment = _build_assessment_service(harness).assess(harness.job_id)
    assert assessment.technical_result_status == "confirmed"
    assert assessment.outcome == FinalizationAssessmentOutcome.TECHNICALLY_SUCCEEDED_RECONCILIATION_PENDING
    assert assessment.last_confirmed_stage == FinalizationStage.AISLE_RECONCILIATION


def test_p3_3_t11_concurrent_evidence_writers_version_conflict(tmp_path) -> None:
    store = MemoryFinalizationStageStore()
    now = datetime(2026, 6, 12, tzinfo=timezone.utc)
    store.transition_stage(
        job_id="job-c",
        stage=FinalizationStage.DOMAIN_RESULTS,
        new_status=StageStatus.IN_PROGRESS,
        evidence_level=EvidenceLevel.CONFIRMED,
        now=now,
    )
    first = store.get_stage("job-c", FinalizationStage.DOMAIN_RESULTS)
    assert first is not None
    store.transition_stage(
        job_id="job-c",
        stage=FinalizationStage.DOMAIN_RESULTS,
        new_status=StageStatus.COMPLETED,
        evidence_level=EvidenceLevel.TRANSACTIONAL,
        completed_at=now,
        expected_version=first.version,
        now=now,
    )
    stale = store.get_stage("job-c", FinalizationStage.DOMAIN_RESULTS)
    assert stale is not None
    from src.application.ports.finalization_stage_store import FinalizationStageConcurrencyError

    with pytest.raises(FinalizationStageConcurrencyError):
        store.transition_stage(
            job_id="job-c",
            stage=FinalizationStage.DOMAIN_RESULTS,
            new_status=StageStatus.IN_PROGRESS,
            evidence_level=EvidenceLevel.CONFIRMED,
            expected_version=first.version,
            now=now,
        )
    final = store.get_stage("job-c", FinalizationStage.DOMAIN_RESULTS)
    assert final is not None
    assert final.status == StageStatus.COMPLETED
    assert final.version == stale.version


def test_p3_3_t12_invalid_stage_transitions_rejected() -> None:
    with pytest.raises(InvalidStageTransitionError):
        assert_stage_transition_allowed(StageStatus.COMPLETED, StageStatus.IN_PROGRESS)
    with pytest.raises(InvalidStageTransitionError):
        assert_stage_transition_allowed(StageStatus.COMPLETED, StageStatus.NOT_STARTED)


def test_p3_3_t13_historical_job_unknown_evidence(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_id="job-hist")
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    job.status = JobStatus.SUCCEEDED
    job.finalization_status = FinalizationStatus.COMPLETED
    harness.job_repo.save(job)
    assessment = _build_assessment_service(harness).assess(harness.job_id)
    domain = assessment.stages[FinalizationStage.DOMAIN_RESULTS.value]
    assert domain.status == StageStatus.UNKNOWN
    assert domain.evidence_level == EvidenceLevel.UNKNOWN
    assert assessment.outcome != FinalizationAssessmentOutcome.COMPLETE


def test_p3_3_t14_api_sanitization_no_raw_exceptions(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path)
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    raw_metadata = {
        "verification_required": True,
        "exception_type": "RuntimeError",
        "failure_message": "marker failed",
        "stack_trace": "secret traceback",
        "storage_secret": "aws-key",
    }
    sanitized = sanitize_finalization_error_metadata(raw_metadata)
    assert sanitized is not None
    assert "stack_trace" not in sanitized
    assert "storage_secret" not in sanitized
    assert sanitized.get("exception_type") == "RuntimeError"
    assessment = _build_assessment_service(harness).assess(harness.job_id)
    assert isinstance(assessment, FinalizationAssessment)
    for stage_view in assessment.stages.values():
        assert isinstance(stage_view, StageAssessment)
        assert stage_view.last_error_code is None or isinstance(stage_view.last_error_code, str)


def test_p3_3_t15_projection_failure_preserves_authoritative_stage(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_id="job-proj")
    now = harness.now
    harness.stage_store.transition_stage(
        job_id=harness.job_id,
        stage=FinalizationStage.DOMAIN_RESULTS,
        new_status=StageStatus.COMPLETED,
        evidence_level=EvidenceLevel.TRANSACTIONAL,
        completed_at=now,
        now=now,
    )
    failing_repo = MagicMock()
    failing_repo.get_by_id.return_value = harness.job_repo.get_by_id(harness.job_id)
    failing_repo.save.side_effect = RuntimeError("projection save failed")
    projection = FinalizationProjectionService(
        job_repo=failing_repo,
        stage_store=harness.stage_store,
        clock=FixedClock(now),
    )
    projection.refresh_summary(harness.job_id)
    stage = harness.stage_store.get_stage(harness.job_id, FinalizationStage.DOMAIN_RESULTS)
    assert stage is not None and stage.status == StageStatus.COMPLETED
    assessment = _build_assessment_service(harness).assess(harness.job_id)
    assert assessment.stages[FinalizationStage.DOMAIN_RESULTS.value].status == StageStatus.COMPLETED


def test_p3_3_corr_t01_api_import_smoke() -> None:
    import subprocess
    import sys
    from pathlib import Path

    backend_root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [sys.executable, "-c", "from src.api.server import app; print('api_import_ok')"],
        cwd=str(backend_root),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "api_import_ok" in result.stdout


def test_p3_3_corr_t02_one_required_artifact_missing(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_id="job-one-req")
    now = harness.now
    harness.manifest_store.mark_published(
        job_id=harness.job_id,
        artifact_kind=ARTIFACT_KIND_EXECUTION_LOG,
        storage_key="logs/exec.jsonl",
        size_bytes=10,
        content_hash=None,
        required=True,
        now=now,
    )
    assert not harness.manifest_store.required_kinds_published(harness.job_id)
    assert ARTIFACT_KIND_HYBRID_REPORT_JSON in harness.manifest_store.missing_required_kinds(
        harness.job_id
    )
    assessment = _build_assessment_service(harness).assess(harness.job_id)
    assert assessment.outcome != FinalizationAssessmentOutcome.COMPLETE


def test_p3_3_corr_t03_required_artifact_pending(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_id="job-pending")
    harness.manifest_store.ensure_expected_entries(harness.job_id, now=harness.now)
    assert not harness.manifest_store.required_kinds_published(harness.job_id)


def test_p3_3_corr_t11_inventory_complete_missing_intermediate(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_status=JobStatus.SUCCEEDED)
    now = harness.now
    harness.stage_store.transition_stage(
        job_id=harness.job_id,
        stage=FinalizationStage.INVENTORY_RECONCILIATION,
        new_status=StageStatus.COMPLETED,
        evidence_level=EvidenceLevel.CONFIRMED,
        completed_at=now,
        now=now,
    )
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    job.status = JobStatus.SUCCEEDED
    harness.job_repo.save(job)
    assessment = _build_assessment_service(harness).assess(harness.job_id)
    assert assessment.outcome == FinalizationAssessmentOutcome.INCONSISTENT
    assert assessment.blocking_reason == "stage_order_gap"


def test_p3_3_corr_t12_missing_job_with_evidence() -> None:
    store = MemoryFinalizationStageStore()
    manifest = MemoryArtifactManifestStore()
    now = datetime(2026, 6, 12, tzinfo=timezone.utc)
    store.transition_stage(
        job_id="ghost-job",
        stage=FinalizationStage.DOMAIN_RESULTS,
        new_status=StageStatus.COMPLETED,
        evidence_level=EvidenceLevel.TRANSACTIONAL,
        completed_at=now,
        now=now,
    )
    svc = FinalizationAssessmentService(
        job_repo=MemoryJobRepository(),
        aisle_repo=MemoryAisleRepository(),
        stage_store=store,
        manifest_store=manifest,
        domain_verifier=JobDomainResultVerifier(
            aisle_repo=MemoryAisleRepository(),
            position_repo=MemoryPositionRepository(),
            product_repo=MemoryProductRecordRepository(),
            evidence_repo=MemoryEvidenceRepository(),
            raw_label_repo=MemoryRawLabelRepository(),
            normalized_label_repo=MemoryNormalizedLabelRepository(),
            final_count_repo=MemoryFinalCountRepository(),
            stage_store=store,
        ),
        artifact_verifier=JobArtifactVerifier(manifest_store=manifest, artifact_store=None),
    )
    assessment = svc.assess("ghost-job")
    assert assessment.outcome == FinalizationAssessmentOutcome.INCONSISTENT
    assert assessment.recovery_candidate is False
    assert assessment.blocking_reason == "orphan_finalization_evidence"


def test_p3_3_corr_t13_concurrent_create_conflict() -> None:
    store = MemoryFinalizationStageStore()
    now = datetime(2026, 6, 12, tzinfo=timezone.utc)
    store.transition_stage(
        job_id="job-cc",
        stage=FinalizationStage.DOMAIN_RESULTS,
        new_status=StageStatus.IN_PROGRESS,
        evidence_level=EvidenceLevel.POSITIVE_EVIDENCE_ONLY,
        now=now,
    )
    from src.application.ports.finalization_stage_store import FinalizationStageConcurrencyError

    with pytest.raises(FinalizationStageConcurrencyError):
        store.transition_stage(
            job_id="job-cc",
            stage=FinalizationStage.DOMAIN_RESULTS,
            new_status=StageStatus.IN_PROGRESS,
            evidence_level=EvidenceLevel.POSITIVE_EVIDENCE_ONLY,
            expected_version=None,
            now=now,
        )


def test_p3_3_corr_t16_projection_clears_stale_timestamps(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_id="job-clear")
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    job.domain_persisted_at = harness.now
    job.artifacts_published_at = harness.now
    harness.job_repo.save(job)
    _cas_transition(
        harness.stage_store,
        job_id=harness.job_id,
        stage=FinalizationStage.DOMAIN_RESULTS,
        new_status=StageStatus.IN_PROGRESS,
        evidence_level=EvidenceLevel.POSITIVE_EVIDENCE_ONLY,
        now=harness.now,
    )
    _cas_transition(
        harness.stage_store,
        job_id=harness.job_id,
        stage=FinalizationStage.DOMAIN_RESULTS,
        new_status=StageStatus.FAILED,
        evidence_level=EvidenceLevel.CONFIRMED,
        now=harness.now,
    )
    projection = FinalizationProjectionService(
        job_repo=harness.job_repo,
        stage_store=harness.stage_store,
        clock=FixedClock(harness.now),
    )
    projection.refresh_summary(harness.job_id)
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    assert job.domain_persisted_at is None
    assert job.artifacts_published_at is None
