"""Phase 3.2 — robust finalization semantics (metadata, taxonomy, cancellation)."""

from __future__ import annotations

from src.application.ports.operational_job_promotion import PromotionOutcome, PromotionResult
from src.application.services.operational_result_promotion_service import (
    OperationalResultPromotionService,
)
from src.domain.aisle.entities import AisleStatus
from src.domain.jobs.entities import Job, JobStatus
from src.domain.jobs.finalization import (
    CurrentFinalizationStep,
    FinalizationErrorCode,
    FinalizationStatus,
    LastCompletedFinalizationStep,
)
from src.infrastructure.persistence.memory_operational_job_promotion_repository import (
    MemoryOperationalJobPromotionRepository,
)
from src.infrastructure.pipeline.finalization_errors import ArtifactPublishPartialError
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
from tests.support.worker_phase1.doubles import (
    ArtifactUploadSpy,
    FailingArtifactStore,
    FailOnNthSavePositionRepository,
    PartialFailingAisleRepository,
    PartialFailingJobRepository,
    RecordingPipelineRunner,
)
from tests.support.worker_phase1.executor_harness import ExecutorHarness, FixedClock
from tests.support.worker_phase2.recompute_doubles import FailingJobScopedRecomputeFactory


def _assert_persist_rollback(harness: ExecutorHarness) -> None:
    assert len(harness.positions_for_job()) == 0


def _assert_operational_pointer_invariant(harness: ExecutorHarness) -> None:
    aisle = harness.aisle_repo.get_by_id(harness.aisle_id)
    assert aisle is not None
    if aisle.operational_job_id is not None:
        op_job = harness.job_repo.get_by_id(aisle.operational_job_id)
        assert op_job is not None
        assert op_job.status == JobStatus.SUCCEEDED


def test_p3_2_t01_persistence_transaction_failure_metadata(tmp_path) -> None:
    from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository

    inner_pos = MemoryPositionRepository()
    failing_pos = FailOnNthSavePositionRepository(inner_pos, fail_on_call=2)
    harness = ExecutorHarness.build(tmp_path, position_repo=failing_pos)
    executor = harness.make_executor()

    handled = harness.run_with_mock_pipeline(executor)

    assert handled is True
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    assert job.status == JobStatus.FAILED
    assert job.finalization_status == FinalizationStatus.FAILED
    assert job.current_finalization_step == CurrentFinalizationStep.PERSIST_DOMAIN_RESULTS
    assert job.last_completed_finalization_step == LastCompletedFinalizationStep.NONE
    assert job.failure_code == FinalizationErrorCode.DOMAIN_PERSISTENCE_FAILED.value
    assert job.finalization_error_code == FinalizationErrorCode.DOMAIN_PERSISTENCE_FAILED.value
    assert job.domain_persisted_at is None
    _assert_persist_rollback(harness)


def test_p3_2_t02_recompute_failure_classified_as_domain_persistence(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path)
    failing_factory = FailingJobScopedRecomputeFactory()
    executor = harness.make_executor(job_scoped_recompute_factory=failing_factory)

    handled = harness.run_with_mock_pipeline(executor)

    assert handled is True
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    assert job.failure_code == FinalizationErrorCode.DOMAIN_PERSISTENCE_FAILED.value
    assert job.last_completed_finalization_step == LastCompletedFinalizationStep.NONE
    _assert_persist_rollback(harness)


def test_p3_2_t03_artifact_failure_after_commit_metadata(tmp_path) -> None:
    artifact_store = FailingArtifactStore(fail_on_call=1)
    harness = ExecutorHarness.build(tmp_path, artifact_store=artifact_store)
    executor = harness.make_executor()

    handled = harness.run_with_mock_pipeline(executor)

    assert handled is True
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    assert job.status == JobStatus.FAILED
    assert job.failure_code == FinalizationErrorCode.ARTIFACT_PUBLISH_FAILED.value
    assert job.finalization_error_code == FinalizationErrorCode.ARTIFACT_PUBLISH_FAILED.value
    assert job.last_completed_finalization_step == LastCompletedFinalizationStep.DOMAIN_RESULTS_PERSISTED
    assert job.current_finalization_step == CurrentFinalizationStep.PUBLISH_ARTIFACTS
    assert job.domain_persisted_at is not None
    assert len(harness.positions_for_job()) == 2
    aisle = harness.aisle_repo.get_by_id(harness.aisle_id)
    assert aisle is not None
    assert aisle.status == AisleStatus.FAILED
    assert aisle.error_code == FinalizationErrorCode.ARTIFACT_PUBLISH_FAILED.value


def test_p3_2_t04_partial_artifact_publication(tmp_path) -> None:
    artifact_store = FailingArtifactStore(fail_on_call=2, fail_mode="exact")
    harness = ExecutorHarness.build(tmp_path, artifact_store=artifact_store)
    executor = harness.make_executor()

    handled = harness.run_with_mock_pipeline(executor)

    assert handled is True
    assert artifact_store.put_object_calls == 2
    assert len(artifact_store.uploaded_keys) == 1
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    assert job.failure_code == FinalizationErrorCode.ARTIFACT_PUBLISH_PARTIAL.value
    assert job.finalization_error_code == FinalizationErrorCode.ARTIFACT_PUBLISH_PARTIAL.value
    meta = job.finalization_error_metadata or {}
    assert "published_artifacts" in meta
    assert job.last_completed_finalization_step == LastCompletedFinalizationStep.DOMAIN_RESULTS_PERSISTED


def test_p3_2_t05_cancel_before_persist_commit(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_status=JobStatus.STARTING)
    executor = harness.make_executor()
    runner = RecordingPipelineRunner(executor._pipeline_runner, clock=FixedClock(harness.now))
    runner.arm_cancel_before_hybrid_run(job_repo=harness.job_repo, job_id=harness.job_id)
    executor._pipeline_runner = runner

    handled = harness.run_with_mock_pipeline(executor)

    assert handled is True
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    assert job.status == JobStatus.CANCELED
    assert job.finalization_status == FinalizationStatus.NOT_STARTED
    assert job.failure_code == "CANCELED"
    assert job.last_completed_finalization_step == LastCompletedFinalizationStep.NONE
    assert len(harness.positions_for_job()) == 0


def test_p3_2_t06_cancel_at_artifact_pre_upload_after_persist(tmp_path, monkeypatch) -> None:
    artifact_store = ArtifactUploadSpy()
    harness = ExecutorHarness.build(tmp_path, artifact_store=artifact_store)
    executor = harness.make_executor()
    spied_persist = executor._persist_use_case.execute

    def persist_then_request_cancel(cmd):  # type: ignore[no-untyped-def]
        spied_persist(cmd)
        job = harness.job_repo.get_by_id(harness.job_id)
        assert job is not None
        job.status = JobStatus.CANCEL_REQUESTED
        job.cancel_requested_at = harness.now
        harness.job_repo.save(job)

    monkeypatch.setattr(executor._persist_use_case, "execute", persist_then_request_cancel)

    handled = harness.run_with_mock_pipeline(executor)

    assert handled is True
    assert artifact_store.put_object_calls == 0
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    assert job.status == JobStatus.CANCELED
    assert job.finalization_status == FinalizationStatus.CANCELED
    assert job.failure_code == FinalizationErrorCode.FINALIZATION_CANCELED.value
    assert job.last_completed_finalization_step == LastCompletedFinalizationStep.DOMAIN_RESULTS_PERSISTED
    assert len(harness.positions_for_job()) == 2
    aisle = harness.aisle_repo.get_by_id(harness.aisle_id)
    assert aisle is not None
    assert aisle.error_code == "CANCELED"


def test_p3_2_t07_job_terminalization_failure(tmp_path) -> None:
    artifact_store = ArtifactUploadSpy()
    inner_job = MemoryJobRepository()
    failing_job = PartialFailingJobRepository(inner_job)
    harness = ExecutorHarness.build(tmp_path, job_repo=failing_job, artifact_store=artifact_store)
    executor = harness.make_executor()

    handled = harness.run_with_mock_pipeline(executor)

    assert handled is True
    job = inner_job.get_by_id(harness.job_id)
    assert job is not None
    assert job.status == JobStatus.FAILED
    assert job.failure_code == FinalizationErrorCode.JOB_TERMINALIZATION_FAILED.value
    assert job.last_completed_finalization_step == LastCompletedFinalizationStep.ARTIFACTS_PUBLISHED
    assert job.current_finalization_step == CurrentFinalizationStep.TERMINALIZE_JOB
    assert job.domain_persisted_at is not None
    assert len(artifact_store.uploaded_keys) >= 2


def test_p3_2_t08_aisle_update_failure(tmp_path) -> None:
    artifact_store = ArtifactUploadSpy()
    inner_aisle = MemoryAisleRepository()
    failing_aisle = PartialFailingAisleRepository(inner_aisle)
    harness = ExecutorHarness.build(tmp_path, aisle_repo=failing_aisle, artifact_store=artifact_store)
    executor = harness.make_executor()

    handled = harness.run_with_mock_pipeline(executor)

    assert handled is True
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    assert job.status == JobStatus.SUCCEEDED
    assert job.finalization_status == FinalizationStatus.FAILED
    assert job.failure_code == FinalizationErrorCode.AISLE_RECONCILIATION_FAILED.value
    assert job.finalization_error_code == FinalizationErrorCode.AISLE_RECONCILIATION_FAILED.value
    assert job.last_completed_finalization_step == LastCompletedFinalizationStep.OPERATIONAL_RESULT_PROMOTED
    assert job.current_finalization_step == CurrentFinalizationStep.UPDATE_AISLE
    aisle = inner_aisle.get_by_id(harness.aisle_id)
    assert aisle is not None
    assert aisle.status != AisleStatus.PROCESSED
    _assert_operational_pointer_invariant(harness)


def test_p3_2_t09_inventory_reconciliation_failure(tmp_path, monkeypatch) -> None:
    artifact_store = ArtifactUploadSpy()
    harness = ExecutorHarness.build(tmp_path, artifact_store=artifact_store)
    executor = harness.make_executor()
    reconcile_calls: list[str] = []
    original_reconcile = executor._state._inventory_status_reconciler.reconcile

    def fail_on_second(inv_id: str) -> bool:
        reconcile_calls.append(inv_id)
        if len(reconcile_calls) == 2:
            raise RuntimeError("simulated inventory reconcile failure")
        return original_reconcile(inv_id)

    monkeypatch.setattr(
        executor._state._inventory_status_reconciler,
        "reconcile",
        fail_on_second,
    )

    handled = harness.run_with_mock_pipeline(executor)

    assert handled is True
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    assert job.status == JobStatus.SUCCEEDED
    assert job.finalization_status == FinalizationStatus.FAILED
    assert job.failure_code == FinalizationErrorCode.INVENTORY_RECONCILIATION_FAILED.value
    assert job.finalization_error_code == FinalizationErrorCode.INVENTORY_RECONCILIATION_FAILED.value
    assert job.last_completed_finalization_step == LastCompletedFinalizationStep.AISLE_UPDATED
    assert job.current_finalization_step == CurrentFinalizationStep.RECONCILE_INVENTORY
    _assert_operational_pointer_invariant(harness)


def test_p3_2_t10_happy_path_finalization_progression(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    executor = harness.make_executor()

    handled = harness.run_with_mock_pipeline(executor)

    assert handled is True
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    assert job.status == JobStatus.SUCCEEDED
    assert job.finalization_status == FinalizationStatus.COMPLETED
    assert job.last_completed_finalization_step == LastCompletedFinalizationStep.INVENTORY_RECONCILED
    assert job.current_finalization_step is None
    assert job.finalization_error_code is None
    assert job.finalization_error_metadata is None
    assert job.domain_persisted_at is not None
    assert job.artifacts_published_at is not None
    assert job.finalization_completed_at is not None
    assert job.result_json is not None
    assert "durable_artifacts" in job.result_json
    aisle = harness.aisle_repo.get_by_id(harness.aisle_id)
    assert aisle is not None
    assert aisle.status == AisleStatus.PROCESSED
    _assert_operational_pointer_invariant(harness)


def test_p3_2_t11_historical_job_without_finalization_fields_readable() -> None:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    legacy = Job(
        id="legacy-job",
        target_type="aisle",
        target_id="a1",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={},
        created_at=now,
        updated_at=now,
    )
    assert legacy.finalization_status == FinalizationStatus.NOT_STARTED
    assert legacy.last_completed_finalization_step == LastCompletedFinalizationStep.NONE
    assert legacy.finalization_error_code is None


def test_p3_2_t12_cancellation_not_swallowed_by_artifact_partial_handler() -> None:
    err = ArtifactPublishPartialError(
        "partial",
        published={"execution_log": {"storage_key": "k"}},
        failed_kind="hybrid_report_json",
    )
    assert isinstance(err, Exception)
    from src.pipeline.errors import PipelineCancellationRequestedError

    cancel = PipelineCancellationRequestedError("cancel")
    assert not isinstance(cancel, ArtifactPublishPartialError)


class _HardFailPromotionService(OperationalResultPromotionService):
    def promote_for_success(self, *, aisle_id: str, candidate_job_id: str) -> PromotionResult:
        return PromotionResult(
            outcome=PromotionOutcome.CONFLICT,
            previous_job_id="other",
            operational_job_id="other",
        )


def test_p3_2_t07b_operational_promotion_hard_failure(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    promotion_svc = _HardFailPromotionService(
        aisle_repo=harness.aisle_repo,
        job_repo=harness.job_repo,
        promotion_repo=MemoryOperationalJobPromotionRepository(
            aisle_repo=harness.aisle_repo,
            job_repo=harness.job_repo,
        ),
    )
    executor = harness.make_executor(operational_promotion_service=promotion_svc)

    handled = harness.run_with_mock_pipeline(executor)

    assert handled is True
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    assert job.status == JobStatus.SUCCEEDED
    assert job.finalization_status == FinalizationStatus.FAILED
    assert job.failure_code == FinalizationErrorCode.OPERATIONAL_PROMOTION_FAILED.value
    assert job.last_completed_finalization_step == LastCompletedFinalizationStep.JOB_TERMINALIZED
    assert job.current_finalization_step == CurrentFinalizationStep.PROMOTE_OPERATIONAL_RESULT
    aisle = harness.aisle_repo.get_by_id(harness.aisle_id)
    assert aisle is not None
    assert aisle.operational_job_id != harness.job_id
    _assert_operational_pointer_invariant(harness)


def test_p3_2_corr_a_domain_marker_save_fails_after_commit(tmp_path, monkeypatch) -> None:
    harness = ExecutorHarness.build(tmp_path)
    executor = harness.make_executor()
    original_save = harness.job_repo.save
    marker_write_attempts = 0

    def save_fail_on_domain_marker(job: Job) -> None:
        nonlocal marker_write_attempts
        if (
            job.finalization_status == FinalizationStatus.IN_PROGRESS
            and job.domain_persisted_at is not None
            and job.finalization_error_code is None
            and job.current_finalization_step == CurrentFinalizationStep.PUBLISH_ARTIFACTS
        ):
            marker_write_attempts += 1
            if marker_write_attempts == 1:
                raise RuntimeError("simulated domain marker save failure")
        original_save(job)

    monkeypatch.setattr(harness.job_repo, "save", save_fail_on_domain_marker)

    handled = harness.run_with_mock_pipeline(executor)

    assert handled is True
    assert marker_write_attempts == 1
    assert len(harness.positions_for_job()) == 2
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    assert job.failure_code == FinalizationErrorCode.FINALIZATION_METADATA_WRITE_FAILED.value
    assert job.failure_code != FinalizationErrorCode.DOMAIN_PERSISTENCE_FAILED.value
    meta = job.finalization_error_metadata or {}
    assert meta.get("domain_commit_completed") is True
    assert meta.get("verification_required") is True
    assert meta.get("failed_marker") == "DOMAIN_RESULTS_PERSISTED"


def test_p3_2_corr_b_artifact_marker_save_fails_after_upload(tmp_path, monkeypatch) -> None:
    artifact_store = ArtifactUploadSpy()
    harness = ExecutorHarness.build(tmp_path, artifact_store=artifact_store)
    executor = harness.make_executor()
    original_save = harness.job_repo.save
    marker_write_attempts = 0

    def save_fail_on_artifact_marker(job: Job) -> None:
        nonlocal marker_write_attempts
        if (
            job.finalization_status == FinalizationStatus.IN_PROGRESS
            and job.artifacts_published_at is not None
            and job.finalization_error_code is None
            and job.current_finalization_step == CurrentFinalizationStep.TERMINALIZE_JOB
        ):
            marker_write_attempts += 1
            if marker_write_attempts == 1:
                raise RuntimeError("simulated artifact marker save failure")
        original_save(job)

    monkeypatch.setattr(harness.job_repo, "save", save_fail_on_artifact_marker)

    handled = harness.run_with_mock_pipeline(executor)

    assert handled is True
    assert marker_write_attempts == 1
    assert len(artifact_store.uploaded_keys) >= 2
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    assert job.failure_code == FinalizationErrorCode.FINALIZATION_METADATA_WRITE_FAILED.value
    assert job.failure_code not in (
        FinalizationErrorCode.ARTIFACT_PUBLISH_FAILED.value,
        FinalizationErrorCode.ARTIFACT_PUBLISH_PARTIAL.value,
    )
    meta = job.finalization_error_metadata or {}
    assert meta.get("artifact_upload_completed") is True
    assert meta.get("verification_required") is True
    assert meta.get("failed_marker") == "ARTIFACTS_PUBLISHED"
    assert meta.get("published_artifact_kinds")


def test_p3_2_corr_g_failure_reporting_repo_unavailable(tmp_path, monkeypatch, caplog) -> None:
    harness = ExecutorHarness.build(tmp_path)
    executor = harness.make_executor()
    original_save = harness.job_repo.save
    reporting_attempts = 0

    def save_fail_on_finalization_fail(job: Job) -> None:
        nonlocal reporting_attempts
        if job.finalization_status == FinalizationStatus.FAILED:
            reporting_attempts += 1
            raise RuntimeError("simulated persistent job repo failure")
        original_save(job)

    monkeypatch.setattr(harness.job_repo, "save", save_fail_on_finalization_fail)
    failing_factory = FailingJobScopedRecomputeFactory()
    executor = harness.make_executor(job_scoped_recompute_factory=failing_factory)

    with caplog.at_level("CRITICAL"):
        handled = harness.run_with_mock_pipeline(executor)

    assert handled is True
    assert reporting_attempts >= 1
    assert any(
        "finalization_failure_reporting_failed" in rec.message for rec in caplog.records
    )


def test_p3_2_corr_api_sanitizes_finalization_error_metadata() -> None:
    from src.infrastructure.pipeline.job_finalization_tracker import (
        sanitize_finalization_error_metadata,
    )

    sanitized = sanitize_finalization_error_metadata(
        {
            "exception_type": "RuntimeError",
            "failure_message": "boom",
            "domain_commit_completed": True,
            "internal_secret": "must_not_leak",
        }
    )
    assert sanitized is not None
    assert sanitized.get("exception_type") == "RuntimeError"
    assert sanitized.get("domain_commit_completed") is True
    assert "internal_secret" not in sanitized
    assert "failure_message" not in sanitized
