"""Focused tests for :class:`V3JobFinalizationService` (Phase 6 Step 6)."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.application.services.artifact_publication_dispatcher import (
    ArtifactPublicationDispatchResult,
    ArtifactSourceStagingFailedError,
)
from src.domain.jobs.artifact_manifest import ArtifactManifestStatus
from src.domain.jobs.artifact_policy import (
    ARTIFACT_KIND_EXECUTION_LOG,
    ARTIFACT_KIND_HYBRID_REPORT_JSON,
    ARTIFACT_KIND_TRACEABILITY_MANIFEST,
)
from src.domain.jobs.entities import JobStatus
from src.domain.jobs.finalization import CurrentFinalizationStep, FinalizationErrorCode
from src.domain.traceability_artifact.errors import TraceabilityArtifactError
from src.infrastructure.pipeline.finalization_errors import (
    ArtifactPublishError,
    ArtifactPublishPartialError,
    ArtifactStoreUnavailableError,
)
from src.infrastructure.pipeline.job_finalization_tracker import JobFinalizationTracker
from src.infrastructure.pipeline.v3_job_finalization_service import (
    V3JobFinalizationRequest,
    V3JobFinalizationService,
)
from src.pipeline.execution_log import ExecutionLogWriter
from src.pipeline.hybrid_inventory_pipeline import PipelineRunResult
from tests.infrastructure.pipeline.test_v3_job_executor_phase5 import FixedClock
from tests.support.worker_phase1.doubles import ArtifactUploadSpy
from tests.support.worker_phase1.executor_harness import ExecutorHarness


def _build_finalize_request(
    harness: ExecutorHarness,
    executor: Any,
) -> V3JobFinalizationRequest:
    run_dir = harness.seed_run_dir()
    job = harness.job_repo.get_by_id(harness.job_id)
    aisle = harness.aisle_repo.get_by_id(harness.aisle_id)
    assert job is not None and aisle is not None
    exec_log = ExecutionLogWriter(run_dir)
    report_path = run_dir / "hybrid_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))

    def _noop_checkpoint(_stage: str, _substep: str | None, _reason: str) -> None:
        return None

    return V3JobFinalizationRequest(
        job_id=harness.job_id,
        aisle=aisle,
        aisle_id=harness.aisle_id,
        run_dir=run_dir,
        exec_log=exec_log,
        pipeline_result=PipelineRunResult(0, {}),
        report_path=report_path,
        report=report,
        job=job,
        cancellation_checkpoint=_noop_checkpoint,
        cancel_event_emitted={"requested": False, "detected": False, "cancelled": False},
        input_type="photos",
        canonical_traceability_expected=True,
    )


def _build_outbox_tracker(
    harness: ExecutorHarness,
    executor: Any,
) -> JobFinalizationTracker:
    tracker = JobFinalizationTracker(
        job_repo=harness.job_repo,
        clock=FixedClock(harness.now),
        job_id=harness.job_id,
        stage_recorder=executor._stage_recorder,
    )
    tracker.begin()
    return tracker


def _service_from_executor(executor: Any) -> V3JobFinalizationService:
    return executor._finalization_service


def test_finalize_success_persists_domain_then_publishes_then_finalizes(tmp_path: Any) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    executor = harness.make_executor(
        artifact_store=ArtifactUploadSpy(),
        artifact_publication_outbox_store=None,
    )
    service = _service_from_executor(executor)
    req = _build_finalize_request(harness, executor)
    step_order: list[str] = []

    spy_state = MagicMock(wraps=executor._state)
    service._state = spy_state
    original_finalize = spy_state.finalize_success

    def _finalize(*args: Any, **kwargs: Any) -> None:
        step_order.append("finalize_success")
        return original_finalize(*args, **kwargs)

    spy_state.finalize_success = _finalize

    original_persist = service._persist_use_case.execute

    def _persist(cmd: Any) -> None:
        step_order.append("persist_domain_results")
        return original_persist(cmd)

    service._persist_use_case.execute = _persist  # type: ignore[method-assign]

    original_publish = service._artifacts.publish_worker_durables

    def _publish(**kwargs: Any) -> dict[str, dict[str, Any]]:
        step_order.append("publish_durable_artifacts")
        return original_publish(**kwargs)

    service._artifacts.publish_worker_durables = _publish  # type: ignore[method-assign]

    with patch.object(service._traceability_artifact_service, "is_required_for_run", return_value=False):
        assert service.finalize_success(req) is False

    assert step_order.index("persist_domain_results") < step_order.index("publish_durable_artifacts")
    assert step_order.index("publish_durable_artifacts") < step_order.index("finalize_success")
    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    assert job.status == JobStatus.SUCCEEDED


def test_finalize_success_traceability_between_domain_and_artifacts(tmp_path: Any) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    executor = harness.make_executor(artifact_store=ArtifactUploadSpy())
    service = _service_from_executor(executor)
    req = _build_finalize_request(harness, executor)
    step_order: list[str] = []

    original_persist = service._persist_use_case.execute

    def _persist(cmd: Any) -> None:
        step_order.append("persist_domain_results")
        return original_persist(cmd)

    service._persist_use_case.execute = _persist  # type: ignore[method-assign]

    def _trace(**kwargs: Any) -> None:
        step_order.append("generate_traceability_artifacts")
        _ = kwargs

    service._traceability_artifact_service.generate_and_write = _trace  # type: ignore[method-assign]

    dispatcher_spy = MagicMock()

    def _dispatch(**kwargs: Any) -> ArtifactPublicationDispatchResult:
        step_order.append("publish_durable_artifacts")
        _ = kwargs
        return ArtifactPublicationDispatchResult(
            required_complete=True,
            published_kinds={
                ARTIFACT_KIND_EXECUTION_LOG,
                ARTIFACT_KIND_HYBRID_REPORT_JSON,
                ARTIFACT_KIND_TRACEABILITY_MANIFEST,
            },
            durable_meta={
                ARTIFACT_KIND_EXECUTION_LOG: {"storage_key": "jobs/x/run/execution_log.jsonl"},
                ARTIFACT_KIND_HYBRID_REPORT_JSON: {"storage_key": "jobs/x/run/hybrid_report.json"},
                ARTIFACT_KIND_TRACEABILITY_MANIFEST: {"storage_key": "jobs/x/run/traceability.json"},
            },
        )

    dispatcher_spy.dispatch_job.side_effect = _dispatch
    service._artifact_dispatcher = dispatcher_spy

    with patch.object(service._traceability_artifact_service, "is_required_for_run", return_value=True):
        service.finalize_success(req)

    assert step_order.index("persist_domain_results") < step_order.index(
        "generate_traceability_artifacts"
    )
    assert step_order.index("generate_traceability_artifacts") < step_order.index(
        "publish_durable_artifacts"
    )


def test_finalize_success_artifact_store_unavailable_after_domain_marks_failed(
    tmp_path: Any,
) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    executor = harness.make_executor(artifact_store=ArtifactUploadSpy())
    service = _service_from_executor(executor)
    req = _build_finalize_request(harness, executor)
    spy_state = MagicMock(wraps=executor._state)
    service._state = spy_state

    with patch.object(service._traceability_artifact_service, "is_required_for_run", return_value=False):
        with patch.object(
            service._artifacts,
            "require_store",
            side_effect=ArtifactStoreUnavailableError("store down"),
        ):
            assert service.finalize_success(req) is True

    spy_state.fail_finalization_and_aisle.assert_called()
    fail_kwargs = spy_state.fail_finalization_and_aisle.call_args.kwargs
    assert fail_kwargs["error_code"] == FinalizationErrorCode.ARTIFACT_STORE_UNAVAILABLE
    spy_state.finalize_success.assert_not_called()
    assert len(harness.positions_for_job()) >= 1


def test_finalize_success_artifact_publish_failure_after_domain(tmp_path: Any) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    executor = harness.make_executor(
        artifact_store=ArtifactUploadSpy(),
        artifact_publication_outbox_store=None,
    )
    service = _service_from_executor(executor)
    req = _build_finalize_request(harness, executor)
    spy_state = MagicMock(wraps=executor._state)
    service._state = spy_state

    with patch.object(service._traceability_artifact_service, "is_required_for_run", return_value=False):
        with patch.object(
            service._artifacts,
            "publish_worker_durables",
            side_effect=ArtifactPublishError("upload failed"),
        ):
            assert service.finalize_success(req) is True

    spy_state.fail_finalization_and_aisle.assert_called_once()
    fail_kwargs = spy_state.fail_finalization_and_aisle.call_args.kwargs
    assert fail_kwargs["error_code"] == FinalizationErrorCode.ARTIFACT_PUBLISH_FAILED
    spy_state.finalize_success.assert_not_called()


def test_finalize_success_traceability_failure_preserved(tmp_path: Any) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    executor = harness.make_executor(artifact_store=ArtifactUploadSpy())
    service = _service_from_executor(executor)
    req = _build_finalize_request(harness, executor)
    spy_state = MagicMock(wraps=executor._state)
    service._state = spy_state

    with patch.object(service._traceability_artifact_service, "is_required_for_run", return_value=True):
        with patch.object(
            service._traceability_artifact_service,
            "generate_and_write",
            side_effect=TraceabilityArtifactError("trace fail", error_code="TRACE_FAIL"),
        ):
            assert service.finalize_success(req) is True

    spy_state.fail_finalization_and_aisle.assert_called_once()
    fail_kwargs = spy_state.fail_finalization_and_aisle.call_args.kwargs
    assert fail_kwargs["error_code"] == FinalizationErrorCode.ARTIFACT_SOURCE_STAGING_FAILED
    spy_state.finalize_success.assert_not_called()


def test_outbox_required_complete_calls_finalize_success(tmp_path: Any) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    executor = harness.make_executor(artifact_store=ArtifactUploadSpy())
    service = _service_from_executor(executor)
    req = _build_finalize_request(harness, executor)
    tracker = _build_outbox_tracker(harness, executor)
    dispatcher = MagicMock()
    service._artifact_dispatcher = dispatcher
    dispatcher.dispatch_job.return_value = ArtifactPublicationDispatchResult(
        required_complete=True,
        published_kinds={ARTIFACT_KIND_EXECUTION_LOG, ARTIFACT_KIND_HYBRID_REPORT_JSON},
        durable_meta={
            ARTIFACT_KIND_EXECUTION_LOG: {"storage_key": f"jobs/{harness.job_id}/run/execution_log.jsonl"},
            ARTIFACT_KIND_HYBRID_REPORT_JSON: {
                "storage_key": f"jobs/{harness.job_id}/run/hybrid_report.json"
            },
        },
    )
    spy_state = MagicMock(wraps=executor._state)
    service._state = spy_state

    assert service._publish_artifacts_via_outbox(req, tracker) is False

    spy_state.finalize_success.assert_called_once()
    spy_state.fail_finalization_and_aisle.assert_not_called()


def test_outbox_retry_schedules_without_finalize_success(tmp_path: Any) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    executor = harness.make_executor(artifact_store=ArtifactUploadSpy())
    service = _service_from_executor(executor)
    req = _build_finalize_request(harness, executor)
    tracker = _build_outbox_tracker(harness, executor)
    dispatcher = MagicMock()
    service._artifact_dispatcher = dispatcher
    dispatcher.dispatch_job.return_value = ArtifactPublicationDispatchResult(
        published_kinds={ARTIFACT_KIND_EXECUTION_LOG},
        retry_scheduled_kinds={ARTIFACT_KIND_HYBRID_REPORT_JSON},
    )
    spy_state = MagicMock(wraps=executor._state)
    service._state = spy_state

    assert service._publish_artifacts_via_outbox(req, tracker) is False

    spy_state.mark_artifact_publication_retry_pending.assert_called_once()
    spy_state.finalize_success.assert_not_called()


def test_outbox_permanent_failure_calls_fail_finalization(tmp_path: Any) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    executor = harness.make_executor(artifact_store=ArtifactUploadSpy())
    service = _service_from_executor(executor)
    req = _build_finalize_request(harness, executor)
    tracker = _build_outbox_tracker(harness, executor)
    dispatcher = MagicMock()
    service._artifact_dispatcher = dispatcher
    dispatcher.dispatch_job.return_value = ArtifactPublicationDispatchResult(
        permanently_failed_kinds={ARTIFACT_KIND_HYBRID_REPORT_JSON},
    )
    spy_state = MagicMock(wraps=executor._state)
    service._state = spy_state

    assert service._publish_artifacts_via_outbox(req, tracker) is True

    spy_state.fail_finalization_and_aisle.assert_called_once()
    assert (
        spy_state.fail_finalization_and_aisle.call_args.kwargs["error_code"]
        == FinalizationErrorCode.ARTIFACT_PUBLISH_FAILED
    )


def test_outbox_partial_required_failure(tmp_path: Any) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    executor = harness.make_executor(artifact_store=ArtifactUploadSpy())
    service = _service_from_executor(executor)
    req = _build_finalize_request(harness, executor)
    tracker = _build_outbox_tracker(harness, executor)
    dispatcher = MagicMock()
    service._artifact_dispatcher = dispatcher
    dispatcher.dispatch_job.return_value = ArtifactPublicationDispatchResult(
        published_kinds={ARTIFACT_KIND_EXECUTION_LOG},
        permanently_failed_kinds={ARTIFACT_KIND_HYBRID_REPORT_JSON},
        durable_meta={
            ARTIFACT_KIND_EXECUTION_LOG: {"storage_key": f"jobs/{harness.job_id}/run/execution_log.jsonl"},
        },
        required_complete=False,
    )
    spy_state = MagicMock(wraps=executor._state)
    service._state = spy_state

    assert service._publish_artifacts_via_outbox(req, tracker) is True

    fail_kwargs = spy_state.fail_finalization_and_aisle.call_args.kwargs
    assert fail_kwargs["error_code"] == FinalizationErrorCode.ARTIFACT_PUBLISH_PARTIAL


def test_outbox_continuation_started_returns_without_finalize_success(tmp_path: Any) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    executor = harness.make_executor(artifact_store=ArtifactUploadSpy())
    service = _service_from_executor(executor)
    req = _build_finalize_request(harness, executor)
    tracker = _build_outbox_tracker(harness, executor)
    dispatcher = MagicMock()
    service._artifact_dispatcher = dispatcher
    dispatcher.dispatch_job.return_value = ArtifactPublicationDispatchResult(
        continuation_started=True,
        required_complete=False,
    )
    spy_state = MagicMock(wraps=executor._state)
    service._state = spy_state

    assert service._publish_artifacts_via_outbox(req, tracker) is False

    spy_state.finalize_success.assert_not_called()
    spy_state.fail_finalization_and_aisle.assert_not_called()


def test_cancel_after_domain_commit_uses_post_commit_path(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    executor = harness.make_executor(artifact_store=ArtifactUploadSpy())
    service = _service_from_executor(executor)
    spy_state = MagicMock(wraps=executor._state)
    service._state = spy_state
    cancel_event_emitted = {"requested": False, "detected": False, "cancelled": False}
    base_req = _build_finalize_request(harness, executor)

    def cancellation_checkpoint(stage: str, substep: str | None, reason: str) -> None:
        spy_state.raise_if_cancellation_requested(
            harness.job_id,
            exec_log=base_req.exec_log,
            inventory_id=base_req.aisle.inventory_id,
            aisle_id=base_req.aisle_id,
            stage=stage,
            substep=substep,
            reason=reason,
            cancel_event_emitted=cancel_event_emitted,
        )

    req = replace(
        base_req,
        cancellation_checkpoint=cancellation_checkpoint,
        cancel_event_emitted=cancel_event_emitted,
        canonical_traceability_expected=False,
    )
    spied_persist = service._persist_use_case.execute

    def persist_then_request_cancel(cmd: Any) -> None:
        spied_persist(cmd)
        job = harness.job_repo.get_by_id(harness.job_id)
        assert job is not None
        job.status = JobStatus.CANCEL_REQUESTED
        job.cancel_requested_at = harness.now
        harness.job_repo.save(job)

    monkeypatch.setattr(service._persist_use_case, "execute", persist_then_request_cancel)

    with patch.object(service._traceability_artifact_service, "is_required_for_run", return_value=False):
        assert service.finalize_success(req) is True

    spy_state.cancel_finalization_after_domain_commit.assert_called_once()
    spy_state.cancel_job_and_aisle.assert_not_called()
    spy_state.finalize_success.assert_not_called()


def test_outbox_staging_failure_calls_fail_finalization(tmp_path: Any) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    executor = harness.make_executor(artifact_store=ArtifactUploadSpy())
    service = _service_from_executor(executor)
    req = _build_finalize_request(harness, executor)
    tracker = _build_outbox_tracker(harness, executor)
    dispatcher = MagicMock()
    dispatcher.register_publication_work.side_effect = ArtifactSourceStagingFailedError(
        "execution log staging failed",
        error_code="EXECUTION_LOG_STAGING_FAILED",
    )
    service._artifact_dispatcher = dispatcher
    spy_state = MagicMock(wraps=executor._state)
    service._state = spy_state

    assert service._publish_artifacts_via_outbox(req, tracker) is True

    dispatcher.register_publication_work.assert_called_once()
    dispatcher.dispatch_job.assert_not_called()
    spy_state.fail_finalization_and_aisle.assert_called_once()
    fail_kwargs = spy_state.fail_finalization_and_aisle.call_args.kwargs
    assert fail_kwargs["error_code"] == FinalizationErrorCode.ARTIFACT_SOURCE_STAGING_FAILED
    assert fail_kwargs["current_step"] == CurrentFinalizationStep.PUBLISH_ARTIFACTS
    assert fail_kwargs["metadata"]["staging_error_code"] == "EXECUTION_LOG_STAGING_FAILED"
    spy_state.finalize_success.assert_not_called()


def test_outbox_dispatch_exception_after_required_published_marks_metadata_write_failed(
    tmp_path: Any,
) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    executor = harness.make_executor(artifact_store=ArtifactUploadSpy())
    service = _service_from_executor(executor)
    req = _build_finalize_request(harness, executor)
    tracker = _build_outbox_tracker(harness, executor)
    dispatcher = MagicMock()
    dispatcher.dispatch_job.side_effect = RuntimeError("marker failed")
    service._artifact_dispatcher = dispatcher

    published_entry = MagicMock()
    published_entry.artifact_kind = ARTIFACT_KIND_EXECUTION_LOG
    published_entry.status = ArtifactManifestStatus.PUBLISHED
    manifest_store = MagicMock()
    manifest_store.required_kinds_published.return_value = True
    manifest_store.list_entries.return_value = [published_entry]
    service._artifact_manifest_store = manifest_store

    job = harness.job_repo.get_by_id(harness.job_id)
    assert job is not None
    assert job.finalization_error_code is None

    spy_state = MagicMock(wraps=executor._state)
    service._state = spy_state

    assert service._publish_artifacts_via_outbox(req, tracker) is True

    dispatcher.register_publication_work.assert_called_once()
    dispatcher.dispatch_job.assert_called_once()
    spy_state.fail_finalization_and_aisle.assert_called_once()
    fail_kwargs = spy_state.fail_finalization_and_aisle.call_args.kwargs
    assert fail_kwargs["error_code"] == FinalizationErrorCode.FINALIZATION_METADATA_WRITE_FAILED
    assert fail_kwargs["current_step"] == CurrentFinalizationStep.PUBLISH_ARTIFACTS
    metadata = fail_kwargs["metadata"]
    assert metadata["artifact_upload_completed"] is True
    assert metadata["marker_write_completed"] is False
    assert metadata["verification_required"] is True
    assert metadata["failed_marker"] == "ARTIFACTS_PUBLISHED"
    assert metadata["published_artifact_kinds"] == [ARTIFACT_KIND_EXECUTION_LOG]
    spy_state.finalize_success.assert_not_called()


def test_legacy_durable_publish_partial_failure_marks_partial(tmp_path: Any) -> None:
    harness = ExecutorHarness.build(tmp_path, artifact_store=ArtifactUploadSpy())
    executor = harness.make_executor(
        artifact_store=ArtifactUploadSpy(),
        artifact_publication_outbox_store=None,
    )
    service = _service_from_executor(executor)
    req = _build_finalize_request(harness, executor)
    service._artifact_dispatcher = None
    spy_state = MagicMock(wraps=executor._state)
    service._state = spy_state

    published = {
        ARTIFACT_KIND_EXECUTION_LOG: {
            "storage_key": f"jobs/{harness.job_id}/run/execution_log.jsonl",
        },
    }
    partial_err = ArtifactPublishPartialError(
        "partial durable upload",
        published=published,
        failed_kind=ARTIFACT_KIND_HYBRID_REPORT_JSON,
    )

    with patch.object(service._traceability_artifact_service, "is_required_for_run", return_value=False):
        with patch.object(
            service._artifacts,
            "publish_worker_durables",
            side_effect=partial_err,
        ):
            assert service.finalize_success(req) is True

    spy_state.fail_finalization_and_aisle.assert_called_once()
    fail_kwargs = spy_state.fail_finalization_and_aisle.call_args.kwargs
    assert fail_kwargs["error_code"] == FinalizationErrorCode.ARTIFACT_PUBLISH_PARTIAL
    assert fail_kwargs["metadata"]["failed_kind"] == ARTIFACT_KIND_HYBRID_REPORT_JSON
    assert fail_kwargs["metadata"]["published_artifacts"] == published
    spy_state.finalize_success.assert_not_called()
