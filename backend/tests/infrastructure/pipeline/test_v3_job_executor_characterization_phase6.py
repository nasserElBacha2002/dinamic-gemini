"""Phase 6 Step 1 — characterization tests locking V3JobExecutor observable behavior before SOLID refactor."""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.application.services.artifact_publication_dispatcher import (
    ArtifactPublicationDispatchResult,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus
from src.domain.jobs.artifact_policy import (
    ARTIFACT_KIND_EXECUTION_LOG,
    ARTIFACT_KIND_HYBRID_REPORT_JSON,
)
from src.domain.jobs.entities import Job, JobStatus
from src.domain.jobs.finalization import FinalizationErrorCode
from src.infrastructure.pipeline.job_finalization_tracker import JobFinalizationTracker
from src.infrastructure.pipeline.v3_job_executor import (
    RUN_ID,
    V3JobExecutor,
    _V3FinalizeAfterPipelineParams,
)
from src.infrastructure.pipeline.v3_job_monitoring_service import V3JobMonitoringService
from src.jobs.models import JobInput
from src.pipeline.contracts.analysis_context import (
    AnalysisContext,
    VisualReferenceContext,
    analysis_context_to_dict,
)
from src.pipeline.execution_log import ExecutionLogWriter
from src.pipeline.hybrid_inventory_pipeline import PipelineRunResult
from src.pipeline.run_metadata import RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT
from tests.infrastructure.pipeline.test_v3_job_executor_phase5 import (
    FixedClock,
    InMemoryAisleRepo,
    InMemoryInventoryRepo,
    InMemoryJobRepo,
    NoopRepo,
    StubArtifactStorage,
)
from tests.support.worker_phase1.doubles import ArtifactUploadSpy
from tests.support.worker_phase1.executor_harness import ExecutorHarness
from tests.support.worker_phase2.executor_persist_deps import memory_executor_persist_kwargs


def _replace_executor_state(executor: V3JobExecutor, spy_state: Any) -> None:
    executor._state = spy_state
    executor._preparation_service._state = spy_state
    executor._monitoring_service._state = spy_state
    executor._cancellation_coordinator._state = spy_state
    executor._pipeline_execution_service._state = spy_state


def _one_photo_asset_repo(aisle_id: str, now: datetime) -> type:
    class _Repo:
        def list_by_aisle(self, aid: str) -> Sequence[SourceAsset]:
            if aid != aisle_id:
                return []
            return [
                SourceAsset(
                    id="asset-1",
                    aisle_id=aisle_id,
                    type=SourceAssetType.PHOTO,
                    original_filename="photo.jpg",
                    storage_path="a1/photo.jpg",
                    mime_type="image/jpeg",
                    uploaded_at=now,
                )
            ]

    return _Repo


def _build_coordination_executor(
    tmp_path: Path,
    *,
    job_id: str = "char-success",
    aisle_id: str = "aisle-1",
) -> tuple[V3JobExecutor, InMemoryJobRepo, str, str]:
    now = datetime(2026, 6, 17, 12, 0, 0, tzinfo=timezone.utc)
    job_repo = InMemoryJobRepo()
    job_repo.save(
        Job(
            id=job_id,
            target_type="aisle",
            target_id=aisle_id,
            job_type="process_aisle",
            status=JobStatus.STARTING,
            payload_json={"aisle_id": aisle_id},
            created_at=now,
            updated_at=now,
            execution_id="ex-char",
        )
    )
    aisle_repo = InMemoryAisleRepo()
    aisle_repo.save(
        Aisle(
            id=aisle_id,
            inventory_id="inv-1",
            code="A01",
            status=AisleStatus.CREATED,
            created_at=now,
            updated_at=now,
        )
    )
    inv_repo = InMemoryInventoryRepo()
    inv_repo.save(
        Inventory(
            id="inv-1",
            name="Inv",
            status=InventoryStatus.PROCESSING,
            created_at=now,
            updated_at=now,
            processing_mode=InventoryProcessingMode.TEST,
        )
    )
    noop = NoopRepo()
    executor = V3JobExecutor(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        source_asset_repo=_one_photo_asset_repo(aisle_id, now)(),
        position_repo=noop,
        product_record_repo=noop,
        evidence_repo=noop,
        clock=FixedClock(now),
        inventory_repo=inv_repo,
        supplier_reference_image_repo=noop,
        artifact_store=StubArtifactStorage(),
        **memory_executor_persist_kwargs(raw_label_repo=noop),
    )
    v3_base = tmp_path / "v3_uploads"
    (v3_base / "a1").mkdir(parents=True, exist_ok=True)
    (v3_base / "a1" / "photo.jpg").write_bytes(b"x")
    return executor, job_repo, job_id, aisle_id


def test_characterization_successful_execution_call_order(tmp_path: Path) -> None:
    """Lock high-level orchestration order for a successful aisle job."""
    executor, job_repo, job_id, _aisle_id = _build_coordination_executor(tmp_path)
    call_order: list[str] = []

    real_state = executor._state
    spy_state = MagicMock(wraps=real_state)

    def _mark_running(*args: Any, **kwargs: Any) -> None:
        call_order.append("mark_running")
        return real_state.mark_running(*args, **kwargs)

    def _finalize_success(*args: Any, **kwargs: Any) -> None:
        call_order.append("finalize_success")
        return real_state.finalize_success(*args, **kwargs)

    spy_state.mark_running.side_effect = _mark_running
    spy_state.finalize_success.side_effect = _finalize_success

    spy_runner = MagicMock()
    ac = AnalysisContext(primary_evidence=[], visual_references=[], instructions=[])

    def _record_build_context(*args: Any, **kwargs: Any) -> AnalysisContext:
        call_order.append("resolve_pipeline_inputs")
        return ac

    spy_runner.build_analysis_context.side_effect = _record_build_context
    spy_runner.build_pipeline_input.side_effect = lambda *a, **k: (
        JobInput(
            video_path="",
            mode="hybrid",
            input_type="photos",
            input_manifest_path="input_manifest.json",
            photos_dir="input_photos",
            metadata={"analysis_context": analysis_context_to_dict(ac)},
        ),
        "",
    )

    def _run_side_effect(**kwargs: object) -> PipelineRunResult:
        call_order.append("run_hybrid_pipeline")
        bp = kwargs["base_path"]
        assert isinstance(bp, Path)
        jid = kwargs["job_id"]
        run_dir = bp / str(jid) / RUN_ID
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "execution_log.jsonl").write_bytes(b"{}\n")
        (run_dir / "hybrid_report.json").write_text("{}", encoding="utf-8")
        return PipelineRunResult(0, {})

    spy_runner.run_hybrid_pipeline.side_effect = _run_side_effect

    real_monitoring_service = executor._monitoring_service

    @contextmanager
    def _monitoring_session_spy(req: Any) -> Iterator[Any]:
        call_order.append("begin_monitoring")
        with V3JobMonitoringService.session(real_monitoring_service, req) as handles:
            yield handles

    def _traceability_spy(**kwargs: Any) -> None:
        call_order.append("generate_traceability_artifacts")
        _ = kwargs
        return None

    real_publish = executor._artifacts.publish_worker_durables

    def _publish_spy(**kwargs: Any) -> dict[str, dict[str, Any]]:
        call_order.append("publish_durable_artifacts")
        return real_publish(**kwargs)

    _replace_executor_state(executor, spy_state)
    executor._pipeline_runner = spy_runner
    executor._persist_use_case = MagicMock()
    executor._persist_use_case.execute.side_effect = lambda cmd: call_order.append(
        "persist_domain_results"
    )
    executor._traceability_artifact_service.generate_and_write = _traceability_spy  # type: ignore[method-assign]
    executor._artifacts.publish_worker_durables = _publish_spy  # type: ignore[method-assign]

    class _FakePipeline:
        def process_video(self, *args: object, **kwargs: object) -> PipelineRunResult:
            raise AssertionError("executor should use runner.run_hybrid_pipeline")

    with patch.object(
        executor._traceability_artifact_service,
        "is_required_for_run",
        return_value=False,
    ):
        with patch.object(executor._monitoring_service, "session", _monitoring_session_spy):
            with patch("src.infrastructure.pipeline.v3_job_executor.load_settings") as ms:
                ms.return_value.output_dir = str(tmp_path)
                ms.return_value.artifact_storage_legacy_local_read_enabled = True
                with patch(
                    "src.infrastructure.pipeline.v3_pipeline_execution_service.HybridInventoryPipeline",
                    return_value=_FakePipeline(),
                ):
                    assert executor.execute(tmp_path, job_id) is True

    assert call_order.index("mark_running") < call_order.index("begin_monitoring")
    assert call_order.index("resolve_pipeline_inputs") < call_order.index("begin_monitoring")
    assert call_order.index("begin_monitoring") < call_order.index("run_hybrid_pipeline")
    assert call_order.index("run_hybrid_pipeline") < call_order.index("persist_domain_results")
    assert call_order.index("persist_domain_results") < call_order.index(
        "publish_durable_artifacts"
    )
    assert call_order.index("publish_durable_artifacts") < call_order.index("finalize_success")
    if "generate_traceability_artifacts" in call_order:
        assert call_order.index("persist_domain_results") < call_order.index(
            "generate_traceability_artifacts"
        )
        assert call_order.index("generate_traceability_artifacts") < call_order.index(
            "publish_durable_artifacts"
        )

    updated = job_repo.get_by_id(job_id)
    assert updated is not None
    assert updated.status == JobStatus.SUCCEEDED


def test_characterization_finalization_step_order_before_finalize_success(
    tmp_path: Path,
) -> None:
    """Lock ordering inside finalization: persist → traceability → artifacts → finalize_success."""
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    executor = harness.make_executor(
        artifact_store=ArtifactUploadSpy(),
        artifact_publication_outbox_store=None,
    )
    step_order: list[str] = []

    real_state = executor._state
    original_finalize = real_state.finalize_success

    def _finalize_success(*args: Any, **kwargs: Any) -> None:
        step_order.append("finalize_success")
        return original_finalize(*args, **kwargs)

    real_state.finalize_success = _finalize_success  # type: ignore[method-assign]

    original_persist = executor._persist_use_case.execute

    def _persist_spy(cmd: Any) -> None:
        step_order.append("persist_domain_results")
        return original_persist(cmd)

    executor._persist_use_case.execute = _persist_spy  # type: ignore[method-assign]

    real_traceability_generate = executor._traceability_artifact_service.generate_and_write

    def _traceability_spy(**kwargs: Any) -> None:
        step_order.append("generate_traceability_artifacts")
        return real_traceability_generate(**kwargs)

    executor._traceability_artifact_service.generate_and_write = _traceability_spy  # type: ignore[method-assign]

    real_publish = executor._artifacts.publish_worker_durables

    def _publish_spy(**kwargs: Any) -> dict[str, dict[str, Any]]:
        step_order.append("publish_durable_artifacts")
        return real_publish(**kwargs)

    executor._artifacts.publish_worker_durables = _publish_spy  # type: ignore[method-assign]

    real_tracker_cls = JobFinalizationTracker

    class _RecordingTracker(real_tracker_cls):  # type: ignore[misc,valid-type]
        def record_domain_persisted(self) -> None:
            step_order.append("tracker_domain_persisted")
            return super().record_domain_persisted()

        def record_artifacts_published(self, *, durable_artifacts: dict[str, dict[str, Any]]) -> None:
            step_order.append("tracker_artifacts_published")
            return super().record_artifacts_published(durable_artifacts=durable_artifacts)

    with patch.object(
        executor._traceability_artifact_service,
        "is_required_for_run",
        return_value=False,
    ):
        with patch(
            "src.infrastructure.pipeline.v3_job_executor.JobFinalizationTracker",
            _RecordingTracker,
        ):
            assert harness.run_with_mock_pipeline(executor) is True

    assert step_order.index("persist_domain_results") < step_order.index("tracker_domain_persisted")
    if "generate_traceability_artifacts" in step_order:
        assert step_order.index("tracker_domain_persisted") < step_order.index(
            "generate_traceability_artifacts"
        )
        assert step_order.index("generate_traceability_artifacts") < step_order.index(
            "publish_durable_artifacts"
        )
    else:
        assert step_order.index("tracker_domain_persisted") < step_order.index(
            "publish_durable_artifacts"
        )
    assert step_order.index("publish_durable_artifacts") < step_order.index(
        "tracker_artifacts_published"
    )
    assert step_order.index("tracker_artifacts_published") < step_order.index("finalize_success")
    assert "finalize_success" not in step_order[: step_order.index("persist_domain_results")]

    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    assert job.status == JobStatus.SUCCEEDED


def _build_outbox_executor_params(
    harness: ExecutorHarness,
) -> tuple[V3JobExecutor, _V3FinalizeAfterPipelineParams, JobFinalizationTracker, MagicMock]:
    """Executor with outbox dispatcher replaced by a spy; minimal finalize params for direct branch tests."""
    executor = harness.make_executor(artifact_store=ArtifactUploadSpy())
    run_dir = harness.seed_run_dir()
    job = harness.job_repo.get_by_id(harness.job_id)
    aisle = harness.aisle_repo.get_by_id(harness.aisle_id)
    assert job is not None and aisle is not None
    exec_log = ExecutionLogWriter(run_dir)
    report_path = run_dir / "hybrid_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    tracker = JobFinalizationTracker(
        job_repo=harness.job_repo,
        clock=FixedClock(harness.now),
        job_id=harness.job_id,
        stage_recorder=executor._stage_recorder,
    )
    tracker.begin()

    def _noop_checkpoint(_stage: str, _substep: str | None, _reason: str) -> None:
        return None

    params = _V3FinalizeAfterPipelineParams(
        job_id=harness.job_id,
        aisle=aisle,
        aisle_id=harness.aisle_id,
        run_dir=run_dir,
        exec_log=exec_log,
        result=PipelineRunResult(0, {}),
        report_path=report_path,
        report=report,
        job=job,
        cancellation_checkpoint=_noop_checkpoint,
        cancel_event_emitted={"requested": False, "detected": False, "cancelled": False},
        input_type="photos",
        canonical_traceability_expected=True,
    )
    dispatcher_spy = MagicMock()
    executor._artifact_dispatcher = dispatcher_spy
    return executor, params, tracker, dispatcher_spy


def test_characterization_outbox_publish_success_calls_finalize_success(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    executor, params, tracker, dispatcher = _build_outbox_executor_params(harness)
    durable_meta = {
        ARTIFACT_KIND_EXECUTION_LOG: {"storage_key": f"jobs/{harness.job_id}/run/execution_log.jsonl"},
        ARTIFACT_KIND_HYBRID_REPORT_JSON: {
            "storage_key": f"jobs/{harness.job_id}/run/hybrid_report.json"
        },
    }
    dispatcher.dispatch_job.return_value = ArtifactPublicationDispatchResult(
        required_complete=True,
        published_kinds={ARTIFACT_KIND_EXECUTION_LOG, ARTIFACT_KIND_HYBRID_REPORT_JSON},
        durable_meta=durable_meta,
    )
    spy_state = MagicMock(wraps=executor._state)
    executor._state = spy_state

    assert executor._publish_artifacts_via_outbox(params, tracker) is False

    dispatcher.register_publication_work.assert_called_once()
    dispatcher.dispatch_job.assert_called_once()
    spy_state.finalize_success.assert_called_once()
    spy_state.fail_finalization_and_aisle.assert_not_called()
    spy_state.mark_artifact_publication_retry_pending.assert_not_called()


def test_characterization_outbox_publish_retry_schedules_without_finalize_success(
    tmp_path: Path,
) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    executor, params, tracker, dispatcher = _build_outbox_executor_params(harness)
    dispatcher.dispatch_job.return_value = ArtifactPublicationDispatchResult(
        published_kinds={ARTIFACT_KIND_EXECUTION_LOG},
        retry_scheduled_kinds={ARTIFACT_KIND_HYBRID_REPORT_JSON},
    )
    spy_state = MagicMock(wraps=executor._state)
    executor._state = spy_state

    assert executor._publish_artifacts_via_outbox(params, tracker) is False

    spy_state.mark_artifact_publication_retry_pending.assert_called_once()
    spy_state.finalize_success.assert_not_called()
    spy_state.fail_finalization_and_aisle.assert_not_called()


def test_characterization_outbox_publish_permanent_failure(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    executor, params, tracker, dispatcher = _build_outbox_executor_params(harness)
    dispatcher.dispatch_job.return_value = ArtifactPublicationDispatchResult(
        permanently_failed_kinds={ARTIFACT_KIND_HYBRID_REPORT_JSON},
        failed_entries=[{"artifact_kind": ARTIFACT_KIND_HYBRID_REPORT_JSON}],
    )
    spy_state = MagicMock(wraps=executor._state)
    executor._state = spy_state

    assert executor._publish_artifacts_via_outbox(params, tracker) is True

    spy_state.fail_finalization_and_aisle.assert_called_once()
    fail_kwargs = spy_state.fail_finalization_and_aisle.call_args.kwargs
    assert fail_kwargs["error_code"] == FinalizationErrorCode.ARTIFACT_PUBLISH_FAILED
    spy_state.finalize_success.assert_not_called()


def test_characterization_outbox_publish_partial_failure(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    executor, params, tracker, dispatcher = _build_outbox_executor_params(harness)
    durable_meta = {
        ARTIFACT_KIND_EXECUTION_LOG: {"storage_key": f"jobs/{harness.job_id}/run/execution_log.jsonl"},
    }
    dispatcher.dispatch_job.return_value = ArtifactPublicationDispatchResult(
        published_kinds={ARTIFACT_KIND_EXECUTION_LOG},
        permanently_failed_kinds={ARTIFACT_KIND_HYBRID_REPORT_JSON},
        durable_meta=durable_meta,
        required_complete=False,
    )
    spy_state = MagicMock(wraps=executor._state)
    executor._state = spy_state

    assert executor._publish_artifacts_via_outbox(params, tracker) is True

    spy_state.fail_finalization_and_aisle.assert_called_once()
    fail_kwargs = spy_state.fail_finalization_and_aisle.call_args.kwargs
    assert fail_kwargs["error_code"] == FinalizationErrorCode.ARTIFACT_PUBLISH_PARTIAL
    spy_state.finalize_success.assert_not_called()


def test_characterization_outbox_publish_continuation_returns_without_inline_finalize_success(
    tmp_path: Path,
) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    executor, params, tracker, dispatcher = _build_outbox_executor_params(harness)
    dispatcher.dispatch_job.return_value = ArtifactPublicationDispatchResult(
        continuation_started=True,
        required_complete=False,
    )
    spy_state = MagicMock(wraps=executor._state)
    executor._state = spy_state

    assert executor._publish_artifacts_via_outbox(params, tracker) is False

    spy_state.finalize_success.assert_not_called()
    spy_state.fail_finalization_and_aisle.assert_not_called()
    spy_state.mark_artifact_publication_retry_pending.assert_not_called()


def test_characterization_cancel_after_domain_commit_uses_post_commit_cancellation_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After domain persistence commits, cooperative cancel must not mark success or upload artifacts."""
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    executor = harness.make_executor()
    spy_state = MagicMock(wraps=executor._state)
    executor._state = spy_state
    spied_persist = executor._persist_use_case.execute

    def persist_then_request_cancel(cmd: Any) -> None:
        spied_persist(cmd)
        job = harness.job_repo.get_by_id(harness.job_id)
        assert job is not None
        job.status = JobStatus.CANCEL_REQUESTED
        job.cancel_requested_at = harness.now
        harness.job_repo.save(job)

    monkeypatch.setattr(executor._persist_use_case, "execute", persist_then_request_cancel)

    handled = harness.run_with_mock_pipeline(executor)

    assert handled is True
    spy_state.cancel_finalization_after_domain_commit.assert_called_once()
    spy_state.finalize_success.assert_not_called()
    spy_state.mark_success.assert_not_called()
    assert len(harness.positions_for_job()) == 2
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    assert job.status == JobStatus.CANCELED
    assert job.last_completed_finalization_step.value == "domain_results_persisted"
    aisle = harness.aisle_repo.get_by_id(harness.aisle_id)
    assert aisle is not None
    assert aisle.status == AisleStatus.FAILED


def test_characterization_visual_reference_failure_metadata_before_fail_and_no_pipeline(
    tmp_path: Path,
) -> None:
    """Visual reference resolution failure must persist metadata, then fail, without running pipeline."""
    now = datetime(2026, 6, 17, 12, 0, 0, tzinfo=timezone.utc)
    job_id = "char-vrc-fail"
    aisle_id = "aisle-1"
    job_repo = InMemoryJobRepo()
    job_repo.save(
        Job(
            id=job_id,
            target_type="aisle",
            target_id=aisle_id,
            job_type="process_aisle",
            status=JobStatus.STARTING,
            payload_json={"aisle_id": aisle_id},
            created_at=now,
            updated_at=now,
        )
    )
    aisle_repo = InMemoryAisleRepo()
    aisle_repo.save(
        Aisle(
            id=aisle_id,
            inventory_id="inv-1",
            code="A01",
            status=AisleStatus.CREATED,
            created_at=now,
            updated_at=now,
        )
    )
    noop = NoopRepo()
    executor = V3JobExecutor(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        source_asset_repo=_one_photo_asset_repo(aisle_id, now)(),
        position_repo=noop,
        product_record_repo=noop,
        evidence_repo=noop,
        clock=FixedClock(now),
        inventory_repo=noop,
        supplier_reference_image_repo=noop,
        **memory_executor_persist_kwargs(raw_label_repo=noop),
    )
    v3_base = tmp_path / "v3_uploads"
    (v3_base / "a1").mkdir(parents=True, exist_ok=True)
    (v3_base / "a1" / "photo.jpg").write_bytes(b"fake")

    failing_context = AnalysisContext(
        primary_evidence=[],
        visual_references=[
            VisualReferenceContext(
                reference_id="ref-missing",
                source_path="inventories/inv-1/visual_references/ref-missing.jpg",
                mime_type="image/jpeg",
            )
        ],
        instructions=["Use references as context."],
    )

    events: list[str] = []
    original_save = job_repo.save

    def _save_spy(job: Job) -> None:
        if (
            job.id == job_id
            and job.result_json is not None
            and RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT in job.result_json
        ):
            events.append("metadata_persisted")
        original_save(job)

    job_repo.save = _save_spy  # type: ignore[method-assign]

    spy_runner = MagicMock()
    spy_runner.build_analysis_context.return_value = failing_context
    spy_runner.build_pipeline_input.side_effect = FileNotFoundError(
        "visual reference ref-missing not found"
    )
    spy_runner.run_hybrid_pipeline.side_effect = AssertionError("pipeline must not run")
    executor._pipeline_runner = spy_runner

    original_fail = executor._state.fail_job_and_aisle

    def _fail_job_and_aisle(*args: Any, **kwargs: Any) -> None:
        events.append("fail_job_and_aisle")
        return original_fail(*args, **kwargs)

    executor._state.fail_job_and_aisle = _fail_job_and_aisle  # type: ignore[method-assign]

    with patch("src.infrastructure.pipeline.v3_job_executor.load_settings") as mock_settings:
        mock_settings.return_value.output_dir = str(tmp_path)
        handled = executor.execute(tmp_path, job_id)

    assert handled is True
    assert events.index("metadata_persisted") < events.index("fail_job_and_aisle")
    spy_runner.run_hybrid_pipeline.assert_not_called()
    updated_job = job_repo.get_by_id(job_id)
    assert updated_job is not None
    assert updated_job.status == JobStatus.FAILED
    assert updated_job.result_json is not None
    vrc = updated_job.result_json[RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT]
    assert vrc["resolved"] is False
    assert "visual reference ref-missing" in vrc["resolution_error"]
