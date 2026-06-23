"""Unit tests for :class:`V3PipelineExecutionService` (Phase 6 Step 5)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.application.services.supplier_prompt_resolver import SupplierPromptResolution
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.pipeline.v3_pipeline_execution_service import (
    RUN_ID,
    V3PipelineExecutionRequest,
    V3PipelineExecutionService,
)
from src.jobs.models import JobInput
from src.pipeline.contracts.analysis_context import AnalysisContext
from src.pipeline.errors import PipelineCancellationRequestedError
from src.pipeline.hybrid_inventory_pipeline import PipelineRunResult


def _execution_request(tmp_path: Path, *, run_dir: Path | None = None) -> V3PipelineExecutionRequest:
    now = datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc)
    job_id = "pipe-job"
    aisle_id = "aisle-1"
    job = Job(
        id=job_id,
        target_type="aisle",
        target_id=aisle_id,
        job_type="process_aisle",
        status=JobStatus.RUNNING,
        payload_json={"aisle_id": aisle_id},
        created_at=now,
        updated_at=now,
        execution_id="ex-pipe",
        provider_name="gemini",
        model_name="m1",
    )
    aisle = Aisle(
        id=aisle_id,
        inventory_id="inv-1",
        code="A01",
        status=AisleStatus.PROCESSING,
        created_at=now,
        updated_at=now,
    )
    resolved_run_dir = run_dir if run_dir is not None else tmp_path / job_id / RUN_ID
    resolved_run_dir.mkdir(parents=True, exist_ok=True)
    return V3PipelineExecutionRequest(
        base_path=tmp_path,
        job_id=job_id,
        job=job,
        aisle=aisle,
        aisle_id=aisle_id,
        run_dir=resolved_run_dir,
        settings=MagicMock(),
        log=logging.getLogger("pipe-exec-test"),
        pipeline_video_path="",
        job_input=JobInput(
            video_path="",
            mode="hybrid",
            input_type="photos",
            metadata={"inventory_id": "inv-1", "aisle_id": aisle_id},
        ),
        analysis_context=AnalysisContext(primary_evidence=[], visual_references=[], instructions=[]),
        execution_observer=MagicMock(),
        cancellation_checkpoint=MagicMock(),
    )


def _service(
    *,
    state: MagicMock | None = None,
    runner: MagicMock | None = None,
    resolver: MagicMock | None = None,
) -> tuple[V3PipelineExecutionService, MagicMock, MagicMock]:
    state = state or MagicMock()
    runner = runner or MagicMock()
    service = V3PipelineExecutionService(
        state_service=state,
        pipeline_runner=runner,
        supplier_prompt_resolver=resolver,
    )
    return service, state, runner


def test_run_success_returns_report_result_and_path(tmp_path: Path) -> None:
    service, _, runner = _service()
    req = _execution_request(tmp_path)
    report_path = req.run_dir / "hybrid_report.json"
    report_path.write_text(json.dumps({"entities": []}), encoding="utf-8")
    pipeline_result = PipelineRunResult(0, {"k": "v"})
    runner.run_hybrid_pipeline.return_value = pipeline_result

    out = service.run(req)

    assert out is not None
    assert out.report == {"entities": []}
    assert out.pipeline_result is pipeline_result
    assert out.report_path == report_path


def test_run_nonzero_exit_calls_fail_job_and_aisle_and_returns_none(tmp_path: Path) -> None:
    service, state, runner = _service()
    req = _execution_request(tmp_path)
    runner.run_hybrid_pipeline.return_value = PipelineRunResult(2, None)

    assert service.run(req) is None

    state.fail_job_and_aisle.assert_called_once()
    assert req.job_id in state.fail_job_and_aisle.call_args[0]
    assert "code 2" in state.fail_job_and_aisle.call_args[0][2]


def test_run_nonzero_exit_uses_last_stage_error_when_available(tmp_path: Path) -> None:
    service, state, runner = _service()
    req = _execution_request(tmp_path)
    runner.run_hybrid_pipeline.return_value = PipelineRunResult(2, None)

    with patch(
        "src.infrastructure.pipeline.v3_pipeline_execution_service.read_last_stage_error",
        return_value="Provider failed with timeout",
    ):
        assert service.run(req) is None

    message = state.fail_job_and_aisle.call_args[0][2]
    assert "Provider failed with timeout" in message
    assert "exit code 2" in message


def test_run_missing_hybrid_report_calls_fail_job_and_aisle_and_returns_none(
    tmp_path: Path,
) -> None:
    service, state, runner = _service()
    req = _execution_request(tmp_path)
    runner.run_hybrid_pipeline.return_value = PipelineRunResult(0, None)

    assert service.run(req) is None

    state.fail_job_and_aisle.assert_called_once()
    assert "hybrid_report.json" in state.fail_job_and_aisle.call_args[0][2]


def test_run_invalid_hybrid_report_json_propagates_decode_error(tmp_path: Path) -> None:
    service, state, runner = _service()
    req = _execution_request(tmp_path)
    (req.run_dir / "hybrid_report.json").write_text("{not-json", encoding="utf-8")
    runner.run_hybrid_pipeline.return_value = PipelineRunResult(0, None)

    with pytest.raises(json.JSONDecodeError):
        service.run(req)

    state.fail_job_and_aisle.assert_not_called()


def test_run_supplier_prompt_resolution_failure_calls_fail_job_and_aisle(
    tmp_path: Path,
) -> None:
    service, state, runner = _service(resolver=MagicMock())
    req = _execution_request(tmp_path)
    bad = SupplierPromptResolution(
        inventory_id="inv-1",
        aisle_id=req.aisle_id,
        client_id="c1",
        client_supplier_id="s1",
        provider_name="gemini",
        model_name="m1",
        supplier_prompt_config_id=None,
        supplier_prompt_config_version=None,
        editable_instructions=None,
        fallback_used=False,
        fallback_reason=None,
        resolution_status="error",
        warnings=(),
        error_code="CLIENT_SUPPLIER_OWNERSHIP_MISMATCH",
    )
    service._supplier_prompt_resolver.resolve.return_value = bad

    assert service.run(req) is None

    state.fail_job_and_aisle.assert_called_once()
    assert "CLIENT_SUPPLIER_OWNERSHIP_MISMATCH" in state.fail_job_and_aisle.call_args[0][2]
    runner.run_hybrid_pipeline.assert_not_called()


def test_run_propagates_pipeline_cancellation_requested_error(tmp_path: Path) -> None:
    service, state, runner = _service()
    req = _execution_request(tmp_path)
    runner.run_hybrid_pipeline.side_effect = PipelineCancellationRequestedError("cancel in pipeline")

    with pytest.raises(PipelineCancellationRequestedError, match="cancel in pipeline"):
        service.run(req)

    state.fail_job_and_aisle.assert_not_called()


def test_run_passes_cancellation_checkpoint_to_runner_unchanged(tmp_path: Path) -> None:
    service, state, runner = _service()
    req = _execution_request(tmp_path)
    (req.run_dir / "hybrid_report.json").write_text(
        json.dumps({"entities": []}),
        encoding="utf-8",
    )
    runner.run_hybrid_pipeline.return_value = PipelineRunResult(0, {})

    service.run(req)

    passed = runner.run_hybrid_pipeline.call_args.kwargs["cancellation_checkpoint"]
    assert passed is req.cancellation_checkpoint
    state.fail_job_and_aisle.assert_not_called()


def test_run_passes_execution_observer_to_runner_unchanged(tmp_path: Path) -> None:
    service, state, runner = _service()
    req = _execution_request(tmp_path)
    (req.run_dir / "hybrid_report.json").write_text(
        json.dumps({"entities": []}),
        encoding="utf-8",
    )
    runner.run_hybrid_pipeline.return_value = PipelineRunResult(0, {})

    service.run(req)

    passed = runner.run_hybrid_pipeline.call_args.kwargs["execution_observer"]
    assert passed is req.execution_observer
    state.fail_job_and_aisle.assert_not_called()
