"""Phase 3.4 — targeted manual finalization recovery tests."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.application.services.artifact_recovery_source_resolver import (
    ArtifactRecoverySourceResolver,
)
from src.application.services.finalization_assessment_service import FinalizationAssessmentService
from src.application.services.finalization_recovery_eligibility import (
    FinalizationRecoveryEligibility,
)
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.services.job_artifact_verifier import JobArtifactVerifier
from src.application.services.job_domain_result_verifier import JobDomainResultVerifier
from src.application.services.operational_result_promotion_service import (
    OperationalResultPromotionService,
)
from src.application.use_cases.finalization_recovery.recovery_command import RecoveryCommand
from src.application.use_cases.finalization_recovery.resume_job_finalization import (
    FinalizationRecoveryCoordinator,
)
from src.application.use_cases.finalization_recovery.verify_and_republish import (
    FinalizationRecoveryDependencies,
)
from src.domain.jobs.artifact_policy import (
    ARTIFACT_KIND_EXECUTION_LOG,
    ARTIFACT_KIND_HYBRID_REPORT_JSON,
)
from src.domain.jobs.entities import Job, JobStatus
from src.domain.jobs.finalization_evidence import (
    EvidenceLevel,
    FinalizationStage,
    StageStatus,
)
from src.domain.jobs.finalization_recovery import RecoveryOperation, RecoveryOutcome
from src.infrastructure.persistence.memory_finalization_recovery_store import (
    MemoryFinalizationRecoveryStore,
)
from src.infrastructure.persistence.memory_operational_job_promotion_repository import (
    MemoryOperationalJobPromotionRepository,
)
from src.infrastructure.pipeline.worker_durable_artifact_publisher import (
    DEFAULT_V3_WORKER_RUN_SEGMENT,
)
from tests.support.worker_phase1.doubles import ArtifactUploadSpy
from tests.support.worker_phase1.executor_harness import ExecutorHarness, FixedClock


def _cas_transition(store, *, job_id: str, stage: FinalizationStage, now: datetime, **kwargs):
    existing = store.get_stage(job_id, stage)
    return store.transition_stage(
        job_id=job_id,
        stage=stage,
        expected_version=existing.version if existing else None,
        now=now,
        **kwargs,
    )


def _build_coordinator(harness: ExecutorHarness) -> FinalizationRecoveryCoordinator:
    promotion = OperationalResultPromotionService(
        aisle_repo=harness.aisle_repo,
        job_repo=harness.job_repo,
        promotion_repo=MemoryOperationalJobPromotionRepository(
            aisle_repo=harness.aisle_repo,
            job_repo=harness.job_repo,
        ),
    )
    domain_verifier = JobDomainResultVerifier(
        aisle_repo=harness.aisle_repo,
        position_repo=harness.position_repo,
        product_repo=harness.product_repo,
        evidence_repo=harness.evidence_repo,
        raw_label_repo=harness.raw_repo,
        normalized_label_repo=harness.norm_repo,
        final_count_repo=harness.final_repo,
        stage_store=harness.stage_store,
    )
    artifact_verifier = JobArtifactVerifier(
        manifest_store=harness.manifest_store,
        artifact_store=harness.artifact_store,
    )
    assessment = FinalizationAssessmentService(
        job_repo=harness.job_repo,
        aisle_repo=harness.aisle_repo,
        stage_store=harness.stage_store,
        manifest_store=harness.manifest_store,
        domain_verifier=domain_verifier,
        artifact_verifier=artifact_verifier,
    )
    recovery_store = MemoryFinalizationRecoveryStore()
    deps = FinalizationRecoveryDependencies(
        job_repo=harness.job_repo,
        aisle_repo=harness.aisle_repo,
        inventory_repo=harness.inventory_repo,
        stage_store=harness.stage_store,
        manifest_store=harness.manifest_store,
        recovery_store=recovery_store,
        assessment_service=assessment,
        domain_verifier=domain_verifier,
        artifact_verifier=artifact_verifier,
        source_resolver=ArtifactRecoverySourceResolver(
            artifact_verifier=artifact_verifier,
            output_dir=harness.base_path,
        ),
        promotion_service=promotion,
        inventory_reconciler=InventoryStatusReconciler(
            inventory_repo=harness.inventory_repo,
            aisle_repo=harness.aisle_repo,
            clock=FixedClock(harness.now),
        ),
        artifact_store=harness.artifact_store,
        clock=FixedClock(harness.now),
        eligibility=FinalizationRecoveryEligibility(),
    )
    return FinalizationRecoveryCoordinator(deps), recovery_store


def _seed_run_artifacts(base: Path, job_id: str) -> Path:
    run_dir = base / job_id / DEFAULT_V3_WORKER_RUN_SEGMENT
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "execution_log.jsonl").write_text('{"event":"test"}\n', encoding="utf-8")
    (run_dir / "hybrid_report.json").write_text(json.dumps({"entities": []}), encoding="utf-8")
    return run_dir


def _mark_domain_complete(harness: ExecutorHarness) -> None:
    _cas_transition(
        harness.stage_store,
        job_id=harness.job_id,
        stage=FinalizationStage.DOMAIN_RESULTS,
        new_status=StageStatus.COMPLETED,
        evidence_level=EvidenceLevel.TRANSACTIONAL,
        completed_at=harness.now,
        now=harness.now,
    )


def test_p3_4_t01_dry_run_no_mutation(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    coordinator, store = _build_coordinator(harness)
    _mark_domain_complete(harness)
    stages_before = len(harness.stage_store.list_stages(harness.job_id))
    manifest_before = len(harness.manifest_store.list_entries(harness.job_id))
    result = coordinator.execute(
        RecoveryOperation.REPUBLISH_ARTIFACTS,
        RecoveryCommand(job_id=harness.job_id, dry_run=True),
    )
    assert result.dry_run is True
    assert len(harness.stage_store.list_stages(harness.job_id)) == stages_before
    assert len(harness.manifest_store.list_entries(harness.job_id)) == manifest_before
    assert len(store.list_attempts(harness.job_id)) == 0


def test_p3_4_t02_recover_missing_artifact_only(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    coordinator, _ = _build_coordinator(harness)
    _mark_domain_complete(harness)
    run_dir = _seed_run_artifacts(harness.base_path, harness.job_id)
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    job.result_json = {"report_path": str(run_dir / "hybrid_report.json")}
    harness.job_repo.save(job)
    harness.manifest_store.mark_published(
        job_id=harness.job_id,
        artifact_kind=ARTIFACT_KIND_EXECUTION_LOG,
        storage_key="jobs/x/run/execution_log.jsonl",
        size_bytes=10,
        content_hash=None,
        required=True,
        now=harness.now,
    )
    result = coordinator.execute(
        RecoveryOperation.REPUBLISH_ARTIFACTS,
        RecoveryCommand(job_id=harness.job_id),
    )
    assert result.outcome == RecoveryOutcome.RECOVERED
    assert harness.manifest_store.get_entry(harness.job_id, ARTIFACT_KIND_HYBRID_REPORT_JSON)


def test_p3_4_t03_repeated_artifact_recovery_idempotent(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    coordinator, _ = _build_coordinator(harness)
    _mark_domain_complete(harness)
    run_dir = _seed_run_artifacts(harness.base_path, harness.job_id)
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    job.result_json = {"report_path": str(run_dir / "hybrid_report.json")}
    harness.job_repo.save(job)
    cmd = RecoveryCommand(job_id=harness.job_id)
    first = coordinator.execute(RecoveryOperation.REPUBLISH_ARTIFACTS, cmd)
    assert first.outcome == RecoveryOutcome.RECOVERED
    second = coordinator.execute(RecoveryOperation.REPUBLISH_ARTIFACTS, cmd)
    assert second.outcome == RecoveryOutcome.ALREADY_COMPLETE


def test_p3_4_t04_artifact_source_unavailable(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    coordinator, _ = _build_coordinator(harness)
    _mark_domain_complete(harness)
    result = coordinator.execute(
        RecoveryOperation.REPUBLISH_ARTIFACTS,
        RecoveryCommand(job_id=harness.job_id),
    )
    assert result.outcome == RecoveryOutcome.SOURCE_UNAVAILABLE
    stage = harness.stage_store.get_stage(harness.job_id, FinalizationStage.REQUIRED_ARTIFACTS)
    assert stage is None or stage.status != StageStatus.COMPLETED


def test_p3_4_t05_terminalize_after_artifact_recovery(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    coordinator, _ = _build_coordinator(harness)
    _mark_domain_complete(harness)
    run_dir = _seed_run_artifacts(harness.base_path, harness.job_id)
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    job.result_json = {"report_path": str(run_dir / "hybrid_report.json")}
    harness.job_repo.save(job)
    coordinator.execute(
        RecoveryOperation.REPUBLISH_ARTIFACTS,
        RecoveryCommand(job_id=harness.job_id),
    )
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    job.status = JobStatus.RUNNING
    harness.job_repo.save(job)
    result = coordinator.execute(
        RecoveryOperation.TERMINALIZE,
        RecoveryCommand(job_id=harness.job_id),
    )
    assert result.outcome == RecoveryOutcome.RECOVERED
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None and job.status == JobStatus.SUCCEEDED


def test_p3_4_t06_terminalize_already_succeeded_idempotent(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_status=JobStatus.SUCCEEDED)
    coordinator, _ = _build_coordinator(harness)
    _mark_domain_complete(harness)
    now = harness.now
    for kind in (ARTIFACT_KIND_EXECUTION_LOG, ARTIFACT_KIND_HYBRID_REPORT_JSON):
        harness.manifest_store.mark_published(
            job_id=harness.job_id,
            artifact_kind=kind,
            storage_key=f"jobs/{harness.job_id}/run/{kind}",
            size_bytes=10,
            content_hash=None,
            required=True,
            now=now,
        )
    _cas_transition(
        harness.stage_store,
        job_id=harness.job_id,
        stage=FinalizationStage.REQUIRED_ARTIFACTS,
        new_status=StageStatus.COMPLETED,
        evidence_level=EvidenceLevel.CONFIRMED,
        completed_at=now,
        now=now,
    )
    _cas_transition(
        harness.stage_store,
        job_id=harness.job_id,
        stage=FinalizationStage.JOB_TERMINALIZATION,
        new_status=StageStatus.COMPLETED,
        evidence_level=EvidenceLevel.CONFIRMED,
        completed_at=now,
        now=now,
    )
    result = coordinator.execute(
        RecoveryOperation.TERMINALIZE,
        RecoveryCommand(job_id=harness.job_id),
    )
    assert result.outcome == RecoveryOutcome.ALREADY_COMPLETE


def test_p3_4_t07_stale_operational_promotion(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_status=JobStatus.SUCCEEDED, artifact_store=ArtifactUploadSpy())
    coordinator, _ = _build_coordinator(harness)
    now = harness.now
    _mark_domain_complete(harness)
    newer = Job(
        id="newer-op",
        target_type="aisle",
        target_id=harness.aisle_id,
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={"aisle_id": harness.aisle_id},
        created_at=now + timedelta(minutes=5),
        updated_at=now + timedelta(minutes=5),
    )
    harness.job_repo.save(newer)
    aisle = harness.aisle_repo.get_by_id(harness.aisle_id)
    assert aisle is not None
    aisle.operational_job_id = newer.id
    harness.aisle_repo.save(aisle)
    for kind in (ARTIFACT_KIND_EXECUTION_LOG, ARTIFACT_KIND_HYBRID_REPORT_JSON):
        harness.manifest_store.mark_published(
            job_id=harness.job_id,
            artifact_kind=kind,
            storage_key=f"jobs/{harness.job_id}/run/{kind}",
            size_bytes=10,
            content_hash=None,
            required=True,
            now=now,
        )
        harness.artifact_store.uploaded_sizes[f"jobs/{harness.job_id}/run/{kind}"] = 10
    for stage in (
        FinalizationStage.REQUIRED_ARTIFACTS,
        FinalizationStage.JOB_TERMINALIZATION,
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
    result = coordinator.execute(
        RecoveryOperation.PROMOTE,
        RecoveryCommand(job_id=harness.job_id),
    )
    assert result.outcome == RecoveryOutcome.ALREADY_SUPERSEDED


def test_p3_4_t12_inconsistent_assessment_refused(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_status=JobStatus.SUCCEEDED)
    coordinator, _ = _build_coordinator(harness)
    now = harness.now
    _cas_transition(
        harness.stage_store,
        job_id=harness.job_id,
        stage=FinalizationStage.INVENTORY_RECONCILIATION,
        new_status=StageStatus.COMPLETED,
        evidence_level=EvidenceLevel.CONFIRMED,
        completed_at=now,
        now=now,
    )
    result = coordinator.execute(
        RecoveryOperation.RESUME,
        RecoveryCommand(job_id=harness.job_id),
    )
    assert result.outcome == RecoveryOutcome.INCONSISTENT


def test_p3_4_t13_failed_before_domain_commit_refused(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_status=JobStatus.FAILED)
    coordinator, _ = _build_coordinator(harness)
    result = coordinator.execute(
        RecoveryOperation.RESUME,
        RecoveryCommand(job_id=harness.job_id),
    )
    assert result.outcome == RecoveryOutcome.NOT_ELIGIBLE
    assert result.error_code == "failed_before_domain_commit"


def test_p3_4_t14_concurrent_recovery_claim() -> None:
    store = MemoryFinalizationRecoveryStore()
    now = datetime(2026, 6, 12, tzinfo=timezone.utc)
    store.begin_attempt(
        recovery_id="r1",
        job_id="job-a",
        operation=RecoveryOperation.REPUBLISH_ARTIFACTS,
        requested_by="admin",
        source="test",
        initial_assessment_outcome="domain_committed_artifacts_missing",
        initial_blocking_reason=None,
        lease_expires_at=now.replace(minute=now.minute + 5),
        now=now,
    )
    from src.application.ports.finalization_recovery_store import RecoveryLeaseConflictError

    with pytest.raises(RecoveryLeaseConflictError):
        store.begin_attempt(
            recovery_id="r2",
            job_id="job-a",
            operation=RecoveryOperation.TERMINALIZE,
            requested_by="admin2",
            source="test",
            initial_assessment_outcome="domain_committed_artifacts_missing",
            initial_blocking_reason=None,
            lease_expires_at=now.replace(minute=now.minute + 5),
            now=now,
        )


def test_p3_4_t16_audit_sanitization() -> None:
    from src.application.services.finalization_recovery_support import sanitize_recovery_message

    assert sanitize_recovery_message("stack_trace secret password") == "recovery_failed"
    assert sanitize_recovery_message("artifact upload failed") == "artifact upload failed"
