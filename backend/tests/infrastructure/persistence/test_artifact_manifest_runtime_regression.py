"""Regression tests for ArtifactManifestStatus runtime references — Phase 3 corrections."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.application.services.finalization_assessment_service import FinalizationAssessmentService
from src.application.services.finalization_projection_service import FinalizationProjectionService
from src.application.services.job_artifact_verifier import JobArtifactVerifier
from src.application.services.job_domain_result_verifier import JobDomainResultVerifier
from src.domain.jobs.artifact_manifest import ArtifactManifestEntry, ArtifactManifestStatus
from src.domain.jobs.artifact_policy import (
    ALL_EXPECTED_ARTIFACT_KINDS,
    ARTIFACT_KIND_EXECUTION_LOG,
    ARTIFACT_KIND_HYBRID_REPORT_CSV,
    ARTIFACT_KIND_HYBRID_REPORT_JSON,
    REQUIRED_ARTIFACT_KINDS,
)
from src.domain.jobs.entities import JobStatus
from src.domain.jobs.finalization import LastCompletedFinalizationStep
from src.domain.jobs.finalization_evidence import (
    EvidenceLevel,
    FinalizationAssessmentOutcome,
    FinalizationStage,
    StageStatus,
)
from src.infrastructure.persistence.memory_artifact_manifest_store import MemoryArtifactManifestStore
from src.infrastructure.persistence.sql_artifact_manifest_store import SqlArtifactManifestStore
from src.infrastructure.pipeline.finalization_stage_recorder import FinalizationStageRecorder
from src.infrastructure.pipeline.job_finalization_tracker import JobFinalizationTracker
from tests.support.worker_phase1.doubles import ArtifactUploadSpy
from tests.support.worker_phase1.executor_harness import ExecutorHarness, FixedClock


def test_artifact_manifest_runtime_modules_import() -> None:
    from src.infrastructure.persistence import sql_artifact_manifest_store as sql_mod
    from src.infrastructure.pipeline import finalization_stage_recorder as rec_mod

    assert sql_mod.SqlArtifactManifestStore is not None
    assert rec_mod.FinalizationStageRecorder is not None
    assert ArtifactManifestStatus.PENDING.value == "pending"


def test_expected_manifest_pre_registration_pending() -> None:
    store = MemoryArtifactManifestStore()
    now = datetime(2026, 6, 12, tzinfo=timezone.utc)
    store.ensure_expected_entries("job-pre", now=now)
    entries = {e.artifact_kind: e for e in store.list_entries("job-pre")}
    assert set(entries) == set(ALL_EXPECTED_ARTIFACT_KINDS)
    assert entries[ARTIFACT_KIND_EXECUTION_LOG].status == ArtifactManifestStatus.PENDING
    assert entries[ARTIFACT_KIND_EXECUTION_LOG].required is True
    assert entries[ARTIFACT_KIND_HYBRID_REPORT_JSON].status == ArtifactManifestStatus.PENDING
    assert entries[ARTIFACT_KIND_HYBRID_REPORT_JSON].required is True
    assert entries[ARTIFACT_KIND_HYBRID_REPORT_CSV].status == ArtifactManifestStatus.PENDING
    assert entries[ARTIFACT_KIND_HYBRID_REPORT_CSV].required is False


def test_sql_artifact_manifest_store_enum_referenced_at_runtime() -> None:
    from src.infrastructure.persistence.sql_artifact_manifest_store import (
        SqlArtifactManifestStore,
        _row_to_entry,
    )

    row = MagicMock()
    row.job_id = "job-sql"
    row.artifact_kind = ARTIFACT_KIND_EXECUTION_LOG
    row.required = True
    row.status = ArtifactManifestStatus.PUBLISHED.value
    row.storage_key = "jobs/job-sql/run/execution_log.jsonl"
    row.content_hash = None
    row.size_bytes = 12
    row.published_at = datetime(2026, 6, 12, tzinfo=timezone.utc)
    row.attempt_count = 1
    row.last_error = None
    row.version = 1
    row.created_at = datetime(2026, 6, 12, tzinfo=timezone.utc)
    row.updated_at = datetime(2026, 6, 12, tzinfo=timezone.utc)
    entry = _row_to_entry(row)
    assert entry.status == ArtifactManifestStatus.PUBLISHED

    store = SqlArtifactManifestStore(MagicMock())
    now = datetime(2026, 6, 12, tzinfo=timezone.utc)
    cursor = MagicMock()
    stored = ArtifactManifestEntry(
        job_id="job-sql",
        artifact_kind=ARTIFACT_KIND_EXECUTION_LOG,
        required=True,
        status=ArtifactManifestStatus.PENDING,
        created_at=now,
        updated_at=now,
    )

    with patch.object(store, "get_entry", side_effect=[None, stored]):
        with patch(
            "src.infrastructure.persistence.sql_artifact_manifest_store.sql_repository_cursor"
        ) as mock_ctx:
            mock_ctx.return_value.__enter__.return_value = cursor
            mock_ctx.return_value.__exit__.return_value = False
            result = store.mark_pending(
                job_id="job-sql",
                artifact_kind=ARTIFACT_KIND_EXECUTION_LOG,
                required=True,
                now=now,
                expected_version=None,
            )

    assert result.status == ArtifactManifestStatus.PENDING
    insert_args = cursor.execute.call_args.args[1]
    assert insert_args[6] == ArtifactManifestStatus.PENDING.value


def test_record_artifact_manifest_marks_required_artifacts_completed(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    projection = FinalizationProjectionService(
        job_repo=harness.job_repo,
        stage_store=harness.stage_store,
        clock=FixedClock(harness.now),
    )
    recorder = FinalizationStageRecorder(
        stage_store=harness.stage_store,
        projection=projection,
        manifest_store=harness.manifest_store,
        clock=FixedClock(harness.now),
    )
    tracker = JobFinalizationTracker(
        job_id=harness.job_id,
        job_repo=harness.job_repo,
        clock=FixedClock(harness.now),
        stage_recorder=recorder,
    )
    durable_meta = {
        ARTIFACT_KIND_EXECUTION_LOG: {"storage_key": "jobs/x/run/execution_log.jsonl", "file_size_bytes": 10},
        ARTIFACT_KIND_HYBRID_REPORT_JSON: {"storage_key": "jobs/x/run/hybrid_report.json", "file_size_bytes": 20},
    }
    tracker.record_artifacts_published(durable_artifacts=durable_meta)
    entries = {e.artifact_kind: e for e in harness.manifest_store.list_entries(harness.job_id)}
    assert entries[ARTIFACT_KIND_EXECUTION_LOG].status == ArtifactManifestStatus.PUBLISHED
    assert entries[ARTIFACT_KIND_HYBRID_REPORT_JSON].status == ArtifactManifestStatus.PUBLISHED
    stage = harness.stage_store.get_stage(harness.job_id, FinalizationStage.REQUIRED_ARTIFACTS)
    assert stage is not None and stage.status == StageStatus.COMPLETED
    assert harness.manifest_store.required_kinds_published(harness.job_id)


def test_marker_write_failure_after_upload_classifies_metadata_error(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    projection = FinalizationProjectionService(
        job_repo=harness.job_repo,
        stage_store=harness.stage_store,
        clock=FixedClock(harness.now),
    )
    recorder = FinalizationStageRecorder(
        stage_store=harness.stage_store,
        projection=projection,
        manifest_store=harness.manifest_store,
        clock=FixedClock(harness.now),
    )
    harness.stage_store.transition_stage(
        job_id=harness.job_id,
        stage=FinalizationStage.DOMAIN_RESULTS,
        new_status=StageStatus.COMPLETED,
        evidence_level=EvidenceLevel.TRANSACTIONAL,
        completed_at=harness.now,
        now=harness.now,
    )
    tracker = JobFinalizationTracker(
        job_id=harness.job_id,
        job_repo=harness.job_repo,
        clock=FixedClock(harness.now),
        stage_recorder=recorder,
    )

    with patch.object(
        harness.manifest_store,
        "mark_published",
        side_effect=RuntimeError("simulated manifest write failure"),
    ):
        with pytest.raises(RuntimeError, match="simulated manifest write failure"):
            tracker.record_artifacts_published(
                durable_artifacts={
                    ARTIFACT_KIND_EXECUTION_LOG: {
                        "storage_key": "jobs/x/run/execution_log.jsonl",
                        "file_size_bytes": 10,
                    }
                }
            )

    domain = harness.stage_store.get_stage(harness.job_id, FinalizationStage.DOMAIN_RESULTS)
    assert domain is not None and domain.status == StageStatus.COMPLETED
    assessment = FinalizationAssessmentService(
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
    ).assess(harness.job_id)
    assert assessment.outcome == FinalizationAssessmentOutcome.DOMAIN_COMMITTED_ARTIFACTS_MISSING
    assert assessment.recovery_candidate is True


def test_full_happy_path_reaches_succeeded(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    executor = harness.make_executor()
    handled = harness.run_with_mock_pipeline(executor)
    assert handled is True
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    assert job.status == JobStatus.SUCCEEDED
    assert job.finalization_error_code is None
    assert job.last_completed_finalization_step == LastCompletedFinalizationStep.INVENTORY_RECONCILED
    for stage in (
        FinalizationStage.DOMAIN_RESULTS,
        FinalizationStage.REQUIRED_ARTIFACTS,
        FinalizationStage.JOB_TERMINALIZATION,
        FinalizationStage.OPERATIONAL_PROMOTION,
        FinalizationStage.AISLE_RECONCILIATION,
        FinalizationStage.INVENTORY_RECONCILIATION,
    ):
        row = harness.stage_store.get_stage(harness.job_id, stage)
        assert row is not None and row.status == StageStatus.COMPLETED


def test_resume_dry_run_from_domain_committed_artifacts_missing(tmp_path) -> None:
    from src.application.use_cases.finalization_recovery.recovery_command import RecoveryCommand
    from src.application.use_cases.finalization_recovery.resume_job_finalization import (
        FinalizationRecoveryCoordinator,
    )
    from src.domain.jobs.finalization_recovery import RecoveryOperation, RecoveryOutcome
    from tests.infrastructure.pipeline.test_worker_phase3_part4_targeted_recovery import (
        _build_coordinator,
        _mark_domain_complete,
    )

    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    coordinator, _ = _build_coordinator(harness)
    _mark_domain_complete(harness)
    result = coordinator.execute(
        RecoveryOperation.RESUME,
        RecoveryCommand(job_id=harness.job_id, dry_run=True),
    )
    assert result.dry_run is True
    assert result.outcome == RecoveryOutcome.VERIFICATION_REQUIRED
    assert result.new_assessment.outcome == FinalizationAssessmentOutcome.DOMAIN_COMMITTED_ARTIFACTS_MISSING
