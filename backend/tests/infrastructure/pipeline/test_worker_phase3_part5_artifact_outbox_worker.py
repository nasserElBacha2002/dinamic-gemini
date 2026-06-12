"""Phase 3.5 corrections — autonomous artifact publication outbox worker tests."""

from __future__ import annotations

import hashlib
import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from src.application.ports.artifact_publication_outbox_store import (
    ArtifactPublicationSourceConflictError,
    MissingMigrationOrStoreUnavailableError,
)
from src.application.services.automatic_finalization_continuation_use_case import (
    AutomaticFinalizationContinuationUseCase,
)
from src.application.services.artifact_publication_retry_policy import classify_publication_error
from src.domain.jobs.artifact_policy import ARTIFACT_KIND_EXECUTION_LOG, ARTIFACT_KIND_HYBRID_REPORT_JSON
from src.domain.jobs.artifact_publication_outbox import (
    ArtifactPublicationOutboxStatus,
    ArtifactSourceType,
)
from src.domain.jobs.entities import JobStatus
from src.domain.jobs.finalization import FinalizationStatus
from src.domain.jobs.finalization_evidence import EvidenceLevel, FinalizationStage, FinalizationStageRecord, StageStatus
from src.jobs.artifact_publication_worker import ArtifactPublicationOutboxWorker
from tests.infrastructure.pipeline.test_worker_phase3_part5_artifact_outbox import (
    RUN_ID,
    _build_dispatcher,
)
from tests.support.worker_phase1.doubles import ArtifactUploadSpy
from tests.support.worker_phase1.executor_harness import ExecutorHarness, FixedClock


def _seed_domain_complete(harness: ExecutorHarness) -> None:
    harness.stage_store.upsert_stage(
        FinalizationStageRecord(
            job_id=harness.job_id,
            stage=FinalizationStage.DOMAIN_RESULTS,
            status=StageStatus.COMPLETED,
            evidence_level=EvidenceLevel.CONFIRMED,
            completed_at=harness.now,
            created_at=harness.now,
            updated_at=harness.now,
        )
    )


class RetryableUploadFailureStore(ArtifactUploadSpy):
    def __init__(self, *, fail_calls: int = 1) -> None:
        super().__init__()
        self._remaining_failures = fail_calls

    def put_object(self, path: str, file_obj, content_type: str):
        if self._remaining_failures > 0:
            self._remaining_failures -= 1
            raise ConnectionError("simulated storage_unavailable")
        return super().put_object(path, file_obj, content_type)


def test_autonomous_retry_after_worker_exit(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=RetryableUploadFailureStore())
    dispatcher, _, _, _ = _build_dispatcher(harness, max_attempts=5)
    run_dir = harness.seed_run_dir()
    dispatcher.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    result = dispatcher.dispatch_job(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    assert result.retry_scheduled_kinds
    entry = harness.outbox_store.get_entry(harness.job_id, ARTIFACT_KIND_EXECUTION_LOG)
    assert entry is not None
    assert entry.status == ArtifactPublicationOutboxStatus.RETRY_SCHEDULED
    harness.outbox_store.retry_now(
        job_id=harness.job_id,
        artifact_kind=ARTIFACT_KIND_EXECUTION_LOG,
        now=harness.now,
        expected_version=entry.version,
    )
    ok_store = ArtifactUploadSpy()
    dispatcher._artifact_store = ok_store
    dispatcher._reconciler._artifact_store = ok_store
    worker = ArtifactPublicationOutboxWorker(dispatcher=dispatcher, poll_seconds=1, batch_size=10)
    worker.run_once()
    dispatcher.dispatch_job(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    entry = harness.outbox_store.get_entry(harness.job_id, ARTIFACT_KIND_EXECUTION_LOG)
    assert entry is not None and entry.status == ArtifactPublicationOutboxStatus.PUBLISHED


def test_durable_source_survives_restart(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    dispatcher, _, _, _ = _build_dispatcher(harness)
    run_dir = harness.seed_run_dir()
    dispatcher.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    entry = harness.outbox_store.get_entry(harness.job_id, ARTIFACT_KIND_EXECUTION_LOG)
    assert entry is not None and entry.source_type == ArtifactSourceType.EXACT_DURABLE_SOURCE
    staging_key = entry.source_reference
    import shutil

    shutil.rmtree(run_dir)
    dispatcher2, _, _, _ = _build_dispatcher(harness)
    claimed = harness.outbox_store.claim_entry(
        job_id=harness.job_id,
        artifact_kind=ARTIFACT_KIND_EXECUTION_LOG,
        claimed_by="restart-worker",
        lease_expires_at=harness.now + timedelta(seconds=60),
        now=harness.now,
    )
    result = __import__(
        "src.application.services.artifact_publication_dispatcher",
        fromlist=["ArtifactPublicationDispatchResult"],
    ).ArtifactPublicationDispatchResult()
    dispatcher2._publish_claimed(claimed=claimed, result=result)
    assert ARTIFACT_KIND_EXECUTION_LOG in result.published_kinds
    assert harness.staging_store.source_exists(staging_key)


def test_staging_failure_no_retryable_row(tmp_path) -> None:
    from src.application.services.artifact_publication_dispatcher import ArtifactSourceStagingFailedError

    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    dispatcher, _, _, _ = _build_dispatcher(harness)
    empty = harness.base_path / harness.job_id / RUN_ID
    empty.mkdir(parents=True)
    with pytest.raises(ArtifactSourceStagingFailedError):
        dispatcher.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=empty)
    assert harness.outbox_store.get_entry(harness.job_id, ARTIFACT_KIND_HYBRID_REPORT_JSON) is None


def test_continuation_by_job_id_only(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    dispatcher, tracker, _, state = _build_dispatcher(harness)
    run_dir = harness.seed_run_dir()
    _seed_domain_complete(harness)
    aisle = harness.aisle_repo.get_by_id(harness.aisle_id)
    dispatcher.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    dispatcher.dispatch_job(
        job_id=harness.job_id,
        run_segment=RUN_ID,
        run_dir=run_dir,
        tracker=tracker,
        continuation_aisle=aisle,
        report_path=run_dir / "hybrid_report.json",
    )
    use_case = AutomaticFinalizationContinuationUseCase(
        job_repo=harness.job_repo,
        aisle_repo=harness.aisle_repo,
        inventory_repo=harness.inventory_repo,
        manifest_store=harness.manifest_store,
        stage_store=harness.stage_store,
        state_service=state,
        clock=FixedClock(harness.now),
    )
    result = use_case.continue_finalization(harness.job_id)
    assert result.completed
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None and job.status == JobStatus.SUCCEEDED


def test_retry_state_not_permanent_failure(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=RetryableUploadFailureStore())
    dispatcher, tracker, _, state = _build_dispatcher(harness, max_attempts=5)
    run_dir = harness.seed_run_dir()
    dispatcher.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    result = dispatcher.dispatch_job(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    assert result.retry_scheduled_kinds
    assert not result.permanently_failed_kinds
    state.mark_artifact_publication_retry_pending(
        harness.job_id,
        tracker=tracker,
        retry_kinds=result.retry_scheduled_kinds,
    )
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job.status == JobStatus.RUNNING
    assert job.finalization_status == FinalizationStatus.IN_PROGRESS


def test_stale_reconciler_skips_active_outbox_retry(tmp_path) -> None:
    from src.application.services.job_stale_reconciler import JobStaleReconciler

    harness = ExecutorHarness.build(tmp_path, job_status=JobStatus.RUNNING)
    job = harness.job_repo.get_by_id(harness.job_id)
    job.last_heartbeat_at = harness.now - timedelta(hours=1)
    harness.job_repo.save(job)
    harness.outbox_store.ensure_publication_work(
        entry=__import__(
            "src.domain.jobs.artifact_publication_outbox",
            fromlist=["ArtifactPublicationOutboxEntry"],
        ).ArtifactPublicationOutboxEntry(
            id="x",
            job_id=harness.job_id,
            artifact_kind=ARTIFACT_KIND_EXECUTION_LOG,
            required=True,
            source_type=ArtifactSourceType.EXACT_DURABLE_SOURCE,
            source_reference="artifact-staging/x/log/sha",
            max_attempts=5,
        ),
        now=harness.now,
    )
    reconciler = JobStaleReconciler(
        job_repo=harness.job_repo,
        clock=FixedClock(harness.now),
        stale_after_seconds=60,
        artifact_publication_outbox=harness.outbox_store,
    )
    out = reconciler.reconcile(harness.job_repo.get_by_id(harness.job_id))
    assert out is not None and out.status == JobStatus.RUNNING


def test_same_size_different_bytes_not_confirmed(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    run_dir = harness.seed_run_dir()
    log_path = run_dir / "execution_log.jsonl"
    size = log_path.stat().st_size

    class SizeOnlySpy(ArtifactUploadSpy):
        def object_exists(self, key: str) -> bool:
            return True

        def get_object_metadata(self, key: str, *, bucket=None):
            from src.infrastructure.storage.artifact_store import StoredObjectMetadata

            return StoredObjectMetadata(file_size_bytes=size, sha256="0" * 64)

    dispatcher, _, _, _ = _build_dispatcher(harness, artifact_store=SizeOnlySpy())
    dispatcher.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    result = dispatcher.dispatch_job(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    assert ARTIFACT_KIND_EXECUTION_LOG in result.retry_scheduled_kinds


def test_matching_sha256_skips_upload(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    run_dir = harness.seed_run_dir()
    log_path = run_dir / "execution_log.jsonl"
    key = f"jobs/{harness.job_id}/run/execution_log.jsonl"
    sha = hashlib.sha256(log_path.read_bytes()).hexdigest()

    class ConfirmedSpy(ArtifactUploadSpy):
        def __init__(self) -> None:
            super().__init__()
            self.put_calls: list[str] = []
            self.uploaded_sizes[key] = log_path.stat().st_size
            self.uploaded_sha256[key] = sha

        def object_exists(self, key: str) -> bool:
            return key == f"jobs/{harness.job_id}/run/execution_log.jsonl"

        def put_object(self, key, file_obj, content_type):
            self.put_calls.append(key)
            return super().put_object(key, file_obj, content_type)

    store = ConfirmedSpy()
    dispatcher, _, _, _ = _build_dispatcher(harness, artifact_store=store)
    dispatcher.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    result = dispatcher.dispatch_job(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    assert ARTIFACT_KIND_EXECUTION_LOG in result.published_kinds
    assert key not in store.put_calls


def test_etag_and_sha256_stored_separately(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    dispatcher, _, _, _ = _build_dispatcher(harness)
    run_dir = harness.seed_run_dir()
    dispatcher.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    dispatcher.dispatch_job(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    entry = harness.outbox_store.get_entry(harness.job_id, ARTIFACT_KIND_EXECUTION_LOG)
    assert entry is not None
    assert entry.source_sha256
    assert entry.storage_etag == "etag-test"
    assert entry.source_sha256 != entry.storage_etag


def test_programming_exception_permanent_no_retry() -> None:
    code, retryable = classify_publication_error(NameError("broken symbol"))
    assert code == "internal_publication_error"
    assert retryable is False


def test_manifest_success_outbox_cas_reconciled(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    dispatcher, _, _, _ = _build_dispatcher(harness)
    run_dir = harness.seed_run_dir()
    dispatcher.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    claimed = harness.outbox_store.claim_entry(
        job_id=harness.job_id,
        artifact_kind=ARTIFACT_KIND_EXECUTION_LOG,
        claimed_by="t",
        lease_expires_at=harness.now + timedelta(seconds=30),
        now=harness.now,
    )
    result = __import__(
        "src.application.services.artifact_publication_dispatcher",
        fromlist=["ArtifactPublicationDispatchResult"],
    ).ArtifactPublicationDispatchResult()
    dispatcher._publish_claimed(claimed=claimed, run_dir=run_dir, run_segment=RUN_ID, result=result)
    manifest = harness.manifest_store.get_entry(harness.job_id, ARTIFACT_KIND_EXECUTION_LOG)
    assert manifest is not None and manifest.status.value == "published"
    entry = harness.outbox_store.get_entry(harness.job_id, ARTIFACT_KIND_EXECUTION_LOG)
    assert entry is not None and entry.status == ArtifactPublicationOutboxStatus.PUBLISHED


def test_source_hash_conflict_rejected(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    dispatcher, _, _, _ = _build_dispatcher(harness)
    run_dir = harness.seed_run_dir()
    dispatcher.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    run_dir2 = harness.seed_run_dir()
    (run_dir2 / "execution_log.jsonl").write_text("different bytes\n", encoding="utf-8")
    with pytest.raises(ArtifactPublicationSourceConflictError):
        dispatcher.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir2)


def test_concurrent_due_claims_single_winner(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    dispatcher, _, _, _ = _build_dispatcher(harness)
    run_dir = harness.seed_run_dir()
    dispatcher.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    now = harness.now
    batch_a = harness.outbox_store.claim_due_entries(
        claimed_by="a", lease_expires_at=now + timedelta(seconds=30), now=now, limit=10
    )
    batch_b = harness.outbox_store.claim_due_entries(
        claimed_by="b", lease_expires_at=now + timedelta(seconds=30), now=now, limit=10
    )
    kinds_a = {e.artifact_kind for e in batch_a}
    kinds_b = {e.artifact_kind for e in batch_b}
    assert not (kinds_a & kinds_b)


def test_api_without_migration_returns_null_block() -> None:
    from src.api.routes.v3.shared import job_to_detail
    from src.domain.jobs.entities import Job

    class BrokenStore:
        def summary_for_job(self, job_id: str):
            raise MissingMigrationOrStoreUnavailableError("table missing")

    now = datetime(2026, 6, 12, 10, 0, 0, tzinfo=timezone.utc)
    job = Job(
        id="j1",
        job_type="process_aisle",
        target_type="aisle",
        target_id="a1",
        status=JobStatus.RUNNING,
        attempt_count=1,
        payload_json={"aisle_id": "a1"},
        created_at=now,
        updated_at=now,
    )
    detail = job_to_detail(job, artifact_publication_outbox=BrokenStore())
    assert detail.artifact_publication is None


def test_worker_shutdown_leaves_claims_recoverable(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    dispatcher, _, _, _ = _build_dispatcher(harness)
    run_dir = harness.seed_run_dir()
    dispatcher.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    worker = ArtifactPublicationOutboxWorker(dispatcher=dispatcher, poll_seconds=1, batch_size=1)
    worker.request_shutdown()
    assert worker.health.shutdown_requested
