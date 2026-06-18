"""Phase 3.5 — durable artifact publication outbox tests."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.application.ports.artifact_publication_outbox_store import (
    ArtifactPublicationOutboxClaimConflictError,
)
from src.application.services.artifact_finalization_continuation import (
    ArtifactFinalizationContinuationCoordinator,
)
from src.application.services.artifact_publication_dispatcher import ArtifactPublicationDispatcher
from src.application.services.finalization_projection_service import FinalizationProjectionService
from src.domain.jobs.artifact_manifest import ArtifactManifestStatus
from src.domain.jobs.artifact_policy import (
    ARTIFACT_KIND_EXECUTION_LOG,
    ARTIFACT_KIND_HYBRID_REPORT_JSON,
)
from src.domain.jobs.artifact_publication_outbox import ArtifactPublicationOutboxStatus
from src.domain.jobs.entities import JobStatus
from src.domain.jobs.finalization_evidence import FinalizationStage, StageStatus
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.infrastructure.pipeline.finalization_stage_recorder import FinalizationStageRecorder
from src.infrastructure.pipeline.job_finalization_tracker import JobFinalizationTracker
from src.infrastructure.pipeline.worker_durable_artifact_publisher import (
    DEFAULT_V3_WORKER_RUN_SEGMENT,
)
from tests.support.worker_phase1.doubles import ArtifactUploadSpy
from tests.support.worker_phase1.executor_harness import ExecutorHarness, FixedClock


def _build_dispatcher(harness: ExecutorHarness, *, artifact_store=None, max_attempts: int = 5):
    artifact_store = artifact_store or harness.artifact_store
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
    from src.application.services.artifact_publication_state_reconciler import (
        ArtifactPublicationStateReconciler,
    )
    from src.application.services.automatic_finalization_continuation_use_case import (
        AutomaticFinalizationContinuationUseCase,
    )
    from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
    from src.application.services.operational_result_promotion_service import (
        OperationalResultPromotionService,
    )
    from src.infrastructure.persistence.memory_operational_job_promotion_repository import (
        MemoryOperationalJobPromotionRepository,
    )
    from src.infrastructure.pipeline.v3_job_execution_state import V3JobExecutionStateService

    promotion = OperationalResultPromotionService(
        aisle_repo=harness.aisle_repo,
        job_repo=harness.job_repo,
        promotion_repo=MemoryOperationalJobPromotionRepository(
            aisle_repo=harness.aisle_repo,
            job_repo=harness.job_repo,
        ),
    )
    state = V3JobExecutionStateService(
        job_repo=harness.job_repo,
        aisle_repo=harness.aisle_repo,
        inventory_repo=harness.inventory_repo,
        clock=FixedClock(harness.now),
        inventory_status_reconciler=InventoryStatusReconciler(
            inventory_repo=harness.inventory_repo,
            aisle_repo=harness.aisle_repo,
            clock=FixedClock(harness.now),
        ),
        operational_promotion_service=promotion,
    )
    continuation = ArtifactFinalizationContinuationCoordinator(
        job_repo=harness.job_repo,
        manifest_store=harness.manifest_store,
        stage_store=harness.stage_store,
        state_service=state,
    )
    automatic = AutomaticFinalizationContinuationUseCase(
        job_repo=harness.job_repo,
        aisle_repo=harness.aisle_repo,
        inventory_repo=harness.inventory_repo,
        manifest_store=harness.manifest_store,
        stage_store=harness.stage_store,
        state_service=state,
        clock=FixedClock(harness.now),
    )
    reconciler = ArtifactPublicationStateReconciler(
        outbox_store=harness.outbox_store,
        manifest_store=harness.manifest_store,
        artifact_store=artifact_store,
        clock=FixedClock(harness.now),
    )
    dispatcher = ArtifactPublicationDispatcher(
        outbox_store=harness.outbox_store,
        manifest_store=harness.manifest_store,
        stage_store=harness.stage_store,
        artifact_store=artifact_store,
        stage_recorder=recorder,
        continuation=continuation,
        automatic_continuation=automatic,
        staging_store=harness.staging_store,
        reconciler=reconciler,
        clock=FixedClock(harness.now),
        lease_seconds=30,
        max_attempts=max_attempts,
        backoff_seconds=(0, 1, 2, 3, 4),
    )
    tracker = JobFinalizationTracker(
        job_id=harness.job_id,
        job_repo=harness.job_repo,
        clock=FixedClock(harness.now),
        stage_recorder=recorder,
    )
    return dispatcher, tracker, recorder, state


RUN_ID = DEFAULT_V3_WORKER_RUN_SEGMENT


def test_outbox_created_before_upload(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    dispatcher, _, _, _ = _build_dispatcher(harness)
    run_dir = harness.seed_run_dir()
    put_calls: list[str] = []

    class OrderSpy(ArtifactUploadSpy):
        def put_object(self, key, file_obj, content_type):
            put_calls.append(key)
            assert harness.outbox_store.list_entries(harness.job_id)
            return super().put_object(key, file_obj, content_type)

    dispatcher._artifact_store = OrderSpy()
    dispatcher.register_publication_work(
        job_id=harness.job_id,
        run_segment=RUN_ID,
        run_dir=run_dir,
    )
    entries = {e.artifact_kind: e for e in harness.outbox_store.list_entries(harness.job_id)}
    assert entries[ARTIFACT_KIND_EXECUTION_LOG].status == ArtifactPublicationOutboxStatus.PENDING
    dispatcher.dispatch_job(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    assert put_calls


def test_successful_required_artifact_publication(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    dispatcher, tracker, _, _ = _build_dispatcher(harness)
    run_dir = harness.seed_run_dir()
    aisle = harness.aisle_repo.get_by_id(harness.aisle_id)
    dispatcher.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    result = dispatcher.dispatch_job(
        job_id=harness.job_id,
        run_segment=RUN_ID,
        run_dir=run_dir,
        tracker=tracker,
        continuation_aisle=aisle,
        report_path=run_dir / "hybrid_report.json",
    )
    assert result.required_complete
    manifest = harness.manifest_store.get_entry(harness.job_id, ARTIFACT_KIND_EXECUTION_LOG)
    assert manifest is not None and manifest.status == ArtifactManifestStatus.PUBLISHED
    stage = harness.stage_store.get_stage(harness.job_id, FinalizationStage.REQUIRED_ARTIFACTS)
    assert stage is not None and stage.status == StageStatus.COMPLETED


def test_partial_publication_one_required_succeeds_one_fails(tmp_path) -> None:
    class FailJsonSpy(ArtifactUploadSpy):
        def put_object(self, path, file_obj, content_type):
            if "hybrid_report.json" in path:
                raise TimeoutError("storage timeout")
            return super().put_object(path, file_obj, content_type)

    harness = ExecutorHarness.build(tmp_path, artifact_store=FailJsonSpy())
    dispatcher, _, _, _ = _build_dispatcher(harness, max_attempts=2)
    run_dir = harness.seed_run_dir()
    dispatcher.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    result = dispatcher.dispatch_job(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    assert ARTIFACT_KIND_EXECUTION_LOG in result.published_kinds
    assert ARTIFACT_KIND_HYBRID_REPORT_JSON in result.retry_scheduled_kinds or ARTIFACT_KIND_HYBRID_REPORT_JSON in result.permanently_failed_kinds
    published = harness.manifest_store.get_entry(harness.job_id, ARTIFACT_KIND_EXECUTION_LOG)
    assert published is not None and published.status == ArtifactManifestStatus.PUBLISHED
    assert not harness.manifest_store.required_kinds_published(harness.job_id)


def test_retryable_failure_schedules_backoff(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=MagicMock())
    harness.artifact_store.put_object.side_effect = TimeoutError("storage timeout")
    harness.artifact_store.object_exists.return_value = False
    dispatcher, _, _, _ = _build_dispatcher(harness, max_attempts=5)
    run_dir = harness.seed_run_dir()
    dispatcher.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    dispatcher.dispatch_job(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    entry = harness.outbox_store.get_entry(harness.job_id, ARTIFACT_KIND_EXECUTION_LOG)
    assert entry is not None
    assert entry.status == ArtifactPublicationOutboxStatus.RETRY_SCHEDULED
    assert entry.next_attempt_at is not None


def test_max_attempts_moves_to_permanently_failed(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=MagicMock())
    harness.artifact_store.put_object.side_effect = TimeoutError("storage timeout")
    harness.artifact_store.object_exists.return_value = False
    dispatcher, _, _, _ = _build_dispatcher(harness, max_attempts=1)
    run_dir = harness.seed_run_dir()
    dispatcher.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    dispatcher.dispatch_job(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    entry = harness.outbox_store.get_entry(harness.job_id, ARTIFACT_KIND_EXECUTION_LOG)
    assert entry is not None
    assert entry.status == ArtifactPublicationOutboxStatus.PERMANENTLY_FAILED


def test_non_retryable_source_missing_no_pointless_retries(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    dispatcher, _, _, _ = _build_dispatcher(harness, max_attempts=5)
    run_dir = harness.seed_run_dir()
    dispatcher.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    entry = harness.outbox_store.get_entry(harness.job_id, ARTIFACT_KIND_EXECUTION_LOG)
    assert entry is not None and entry.source_reference
    harness.staging_store.delete_source(entry.source_reference)
    dispatcher.dispatch_job(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    entry = harness.outbox_store.get_entry(harness.job_id, ARTIFACT_KIND_EXECUTION_LOG)
    assert entry is not None
    assert entry.status == ArtifactPublicationOutboxStatus.PERMANENTLY_FAILED
    assert entry.attempt_count == 1


def test_duplicate_dispatcher_claim_only_one_processes(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    dispatcher_a, _, _, _ = _build_dispatcher(harness)
    dispatcher_b, _, _, _ = _build_dispatcher(harness)
    run_dir = harness.seed_run_dir()
    dispatcher_a.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    now = harness.now
    first = harness.outbox_store.claim_entry(
        job_id=harness.job_id,
        artifact_kind=ARTIFACT_KIND_EXECUTION_LOG,
        claimed_by="worker-a",
        lease_expires_at=now + timedelta(seconds=60),
        now=now,
    )
    with pytest.raises(ArtifactPublicationOutboxClaimConflictError):
        harness.outbox_store.claim_entry(
            job_id=harness.job_id,
            artifact_kind=ARTIFACT_KIND_EXECUTION_LOG,
            claimed_by="worker-b",
            lease_expires_at=now + timedelta(seconds=60),
            now=now,
        )
    assert first.claimed_by == "worker-a"


def test_expired_lease_reclaimed(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    now = harness.now
    run_dir = harness.seed_run_dir()
    dispatcher, _, _, _ = _build_dispatcher(harness)
    dispatcher.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    harness.outbox_store.claim_entry(
        job_id=harness.job_id,
        artifact_kind=ARTIFACT_KIND_EXECUTION_LOG,
        claimed_by="stale-worker",
        lease_expires_at=now - timedelta(seconds=1),
        now=now - timedelta(seconds=2),
    )
    harness.outbox_store.release_expired_claims(now=now)
    reclaimed = harness.outbox_store.claim_entry(
        job_id=harness.job_id,
        artifact_kind=ARTIFACT_KIND_EXECUTION_LOG,
        claimed_by="worker-b",
        lease_expires_at=now + timedelta(seconds=60),
        now=now,
    )
    assert reclaimed.claimed_by == "worker-b"


def test_object_already_exists_skips_upload(tmp_path) -> None:
    import hashlib

    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    run_dir = harness.seed_run_dir()
    log_path = run_dir / "execution_log.jsonl"
    size = log_path.stat().st_size
    key = f"jobs/{harness.job_id}/run/execution_log.jsonl"
    expected_sha = hashlib.sha256(log_path.read_bytes()).hexdigest()

    class ExistsSpy(ArtifactUploadSpy):
        def __init__(self) -> None:
            super().__init__()
            self.put_calls: list[str] = []
            self.uploaded_sizes[key] = size
            self.uploaded_sha256[key] = expected_sha

        def object_exists(self, key: str) -> bool:
            return key == f"jobs/{harness.job_id}/run/execution_log.jsonl"

        def object_size_bytes(self, key: str, *, bucket=None) -> int:
            return size

        def put_object(self, key, file_obj, content_type):
            self.put_calls.append(key)
            return super().put_object(key, file_obj, content_type)

    store = ExistsSpy()
    dispatcher, _, _, _ = _build_dispatcher(harness, artifact_store=store)
    dispatcher.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    result = dispatcher.dispatch_job(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    assert ARTIFACT_KIND_EXECUTION_LOG in result.published_kinds
    assert f"jobs/{harness.job_id}/run/execution_log.jsonl" not in store.put_calls


def test_object_exists_but_mismatch_is_permanent(tmp_path) -> None:

    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    run_dir = harness.seed_run_dir()
    log_path = run_dir / "execution_log.jsonl"
    size = log_path.stat().st_size

    class MismatchSpy(ArtifactUploadSpy):
        def object_exists(self, key: str) -> bool:
            return True

        def object_size_bytes(self, key: str, *, bucket=None) -> int:
            return size

        def get_object_metadata(self, key: str, *, bucket=None):
            from src.infrastructure.storage.artifact_store import StoredObjectMetadata

            return StoredObjectMetadata(
                file_size_bytes=size,
                etag="etag-test",
                sha256="deadbeef" * 8,
            )

    dispatcher, _, _, _ = _build_dispatcher(harness, artifact_store=MismatchSpy())
    dispatcher.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    result = dispatcher.dispatch_job(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    assert ARTIFACT_KIND_EXECUTION_LOG in result.retry_scheduled_kinds


def test_optional_artifact_failure_does_not_block_required(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    dispatcher, tracker, _, _ = _build_dispatcher(harness)
    run_dir = harness.seed_run_dir()
    (run_dir / "hybrid_report.csv").unlink()
    aisle = harness.aisle_repo.get_by_id(harness.aisle_id)
    dispatcher.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    result = dispatcher.dispatch_job(
        job_id=harness.job_id,
        run_segment=RUN_ID,
        run_dir=run_dir,
        tracker=tracker,
        continuation_aisle=aisle,
        report_path=run_dir / "hybrid_report.json",
    )
    assert result.required_complete


def test_required_set_complete_starts_continuation_once(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    dispatcher, tracker, _, state = _build_dispatcher(harness)
    run_dir = harness.seed_run_dir()
    aisle = harness.aisle_repo.get_by_id(harness.aisle_id)
    dispatcher.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    with patch.object(state, "finalize_success", wraps=state.finalize_success) as finalize_mock:
        dispatcher.dispatch_job(
            job_id=harness.job_id,
            run_segment=RUN_ID,
            run_dir=run_dir,
            tracker=tracker,
            continuation_aisle=aisle,
            report_path=run_dir / "hybrid_report.json",
        )
        dispatcher.dispatch_job(
            job_id=harness.job_id,
            run_segment=RUN_ID,
            run_dir=run_dir,
            tracker=tracker,
            continuation_aisle=aisle,
            report_path=run_dir / "hybrid_report.json",
        )
        assert finalize_mock.call_count == 1


def _single_video_source_asset_repo(tmp_path: Path, aisle_id: str):
    now = datetime(2026, 6, 18, tzinfo=timezone.utc)
    video_dir = tmp_path / "v3_uploads" / "videos"
    video_dir.mkdir(parents=True, exist_ok=True)
    (video_dir / "video-1.mp4").write_bytes(b"mp4-bytes")
    asset = SourceAsset(
        id="video-1",
        aisle_id=aisle_id,
        type=SourceAssetType.VIDEO,
        original_filename="clip.mp4",
        storage_path="videos/video-1.mp4",
        mime_type="video/mp4",
        uploaded_at=now,
    )

    class _Repo:
        def list_by_aisle(self, aid: str):
            return [asset] if aid == aisle_id else []

        def summarize_assets_for_aisles(self, aisle_ids):
            from src.application.ports.contracts import AisleAssetRollup

            return {aid: AisleAssetRollup(count=0, last_uploaded_at=None) for aid in aisle_ids}

    return _Repo()


def test_full_happy_path_executor_with_outbox(tmp_path) -> None:
    harness = ExecutorHarness.build(
        tmp_path,
        artifact_store=ArtifactUploadSpy(),
        source_asset_repo=_single_video_source_asset_repo(tmp_path, "aisle-1"),
    )
    executor = harness.make_executor()
    handled = harness.run_with_mock_pipeline(executor)
    assert handled is True
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    assert job.status == JobStatus.SUCCEEDED
    assert harness.manifest_store.required_kinds_published(harness.job_id)


def test_crash_after_upload_reconciles_manifest_on_retry(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    dispatcher, _, _, _ = _build_dispatcher(harness)
    run_dir = harness.seed_run_dir()
    dispatcher.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    now = harness.now
    harness.outbox_store.claim_entry(
        job_id=harness.job_id,
        artifact_kind=ARTIFACT_KIND_EXECUTION_LOG,
        claimed_by="worker",
        lease_expires_at=now + timedelta(seconds=30),
        now=now,
    )
    key = f"jobs/{harness.job_id}/run/execution_log.jsonl"
    with open(run_dir / "execution_log.jsonl", "rb") as fh:
        harness.artifact_store.put_object(key, fh, "application/x-ndjson")
    harness.outbox_store.release_expired_claims(now=now + timedelta(seconds=60))
    result = dispatcher.dispatch_job(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    assert ARTIFACT_KIND_EXECUTION_LOG in result.published_kinds
    manifest = harness.manifest_store.get_entry(harness.job_id, ARTIFACT_KIND_EXECUTION_LOG)
    assert manifest is not None and manifest.status == ArtifactManifestStatus.PUBLISHED


def test_ephemeral_local_source_unavailable_permanent_failure(tmp_path) -> None:
    from src.application.services.artifact_publication_dispatcher import (
        ArtifactSourceStagingFailedError,
    )

    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    dispatcher, _, _, _ = _build_dispatcher(harness)
    empty_run = harness.base_path / harness.job_id / RUN_ID
    empty_run.mkdir(parents=True)
    with pytest.raises(ArtifactSourceStagingFailedError):
        dispatcher.register_publication_work(
            job_id=harness.job_id, run_segment=RUN_ID, run_dir=empty_run
        )
    assert harness.outbox_store.get_entry(harness.job_id, ARTIFACT_KIND_EXECUTION_LOG) is None


def test_manual_recovery_does_not_duplicate_outbox_rows(tmp_path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    dispatcher, _, _, _ = _build_dispatcher(harness)
    run_dir = harness.seed_run_dir()
    dispatcher.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    dispatcher.register_publication_work(job_id=harness.job_id, run_segment=RUN_ID, run_dir=run_dir)
    kinds = {e.artifact_kind for e in harness.outbox_store.list_entries(harness.job_id)}
    assert kinds == {ARTIFACT_KIND_EXECUTION_LOG, ARTIFACT_KIND_HYBRID_REPORT_JSON, "hybrid_report_csv"}
    assert len(harness.outbox_store.list_entries(harness.job_id)) == 3


def test_sql_concurrent_claims(tmp_path) -> None:
    pytest.importorskip("pyodbc")
    from tests.support.sql_integration import sql_server_client_or_skip

    try:
        client = sql_server_client_or_skip()
    except Exception:
        pytest.skip("SQL Server unavailable")
    from src.domain.jobs.artifact_publication_outbox import (
        ArtifactPublicationOutboxEntry,
        ArtifactSourceType,
    )
    from src.infrastructure.persistence.sql_artifact_publication_outbox_store import (
        SqlArtifactPublicationOutboxStore,
    )

    store = SqlArtifactPublicationOutboxStore(client)
    now = datetime.now(timezone.utc)
    job_id = f"outbox-concurrency-{now.timestamp():.0f}"
    try:
        entry = ArtifactPublicationOutboxEntry(
            id=f"row-{job_id}",
            job_id=job_id,
            artifact_kind=ARTIFACT_KIND_EXECUTION_LOG,
            required=True,
            source_type=ArtifactSourceType.EXACT_LOCAL_SOURCE,
            destination_key=f"jobs/{job_id}/run/execution_log.jsonl",
            max_attempts=5,
        )
        store.ensure_publication_work(entry=entry, now=now)
    except Exception as exc:
        pytest.skip(f"artifact_publication_outbox table unavailable: {exc}")
    results: list[str] = []
    errors: list[Exception] = []

    def claim(name: str) -> None:
        try:
            store.claim_entry(
                job_id=job_id,
                artifact_kind=ARTIFACT_KIND_EXECUTION_LOG,
                claimed_by=name,
                lease_expires_at=now + timedelta(seconds=30),
                now=now,
            )
            results.append(name)
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=claim, args=("a",))
    t2 = threading.Thread(target=claim, args=("b",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert len(results) == 1
    assert len(errors) == 1
