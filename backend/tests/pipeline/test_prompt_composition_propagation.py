"""Phase 6 — ``prompt_composition`` propagation across request, result, run_metadata, and execution log."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.llm.prompt_composer.prompt_traceability import LLM_METADATA_KEY_PROMPT_COMPOSITION
from src.llm.types import LLMRequest, LLMResponse
from src.pipeline.adapters.hybrid_global_analysis_strategy import HybridGlobalAnalysisStrategy
from src.pipeline.context.run_context import RunContext
from src.pipeline.ports.analysis_provider import AnalysisResult
from src.pipeline.run_metadata import RUN_METADATA_KEY_PROMPT_COMPOSITION, build_run_metadata
from src.pipeline.stages.analysis_stage import AnalysisStage, AnalysisStageResult
from src.pipeline.stages.frame_acquisition_stage import AcquiredFrames
from tests.support.llm_executor_harness import (
    HARNESS_RESPONSE_PROVIDER,
    TestLLMExecutor,
    llm_response_success,
    patch_hybrid_resolve_llm_executor,
)


def _video_context(tmp_path: Path) -> RunContext:
    job_input = MagicMock()
    job_input.input_type = "video"
    job_input.metadata = {}
    settings = MagicMock()
    settings.hybrid_prompt = "global_v21"
    settings.debug_log_full_analysis_prompt = False
    run_dir = tmp_path / "j" / "r"
    run_dir.mkdir(parents=True)
    return RunContext(
        job_id="j",
        run_id="r",
        workspace_path=tmp_path,
        run_dir=run_dir,
        job_input=job_input,
        settings=settings,
        logger=MagicMock(),
        execution_log=MagicMock(),
    )


def test_prompt_composition_same_object_request_result_and_run_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """One merged dict is attached to the request, returned on the result, and stored in run_metadata."""
    captured: dict[str, Any] = {}

    def _handler(request: LLMRequest, settings: Any) -> LLMResponse:
        del settings
        captured["request"] = request
        return llm_response_success(parsed_json={"total_entities_detected": 0, "entities": []})

    executor = TestLLMExecutor(handler=_handler)
    patch_hybrid_resolve_llm_executor(monkeypatch, executor)
    context = _video_context(tmp_path)
    strategy = HybridGlobalAnalysisStrategy()
    result = strategy.analyze(
        context=context,
        frames_nd=[np.zeros((8, 8, 3), dtype=np.uint8)],
        frame_paths=[Path("/tmp/f.jpg")],
        frame_refs=["f0"],
        metadata={"frame_count": 1},
    )
    req = captured["request"]
    pc_req = req.metadata.get(LLM_METADATA_KEY_PROMPT_COMPOSITION)
    assert pc_req is not None
    assert pc_req is result.prompt_composition
    rm = build_run_metadata(None, None, prompt_composition=result.prompt_composition)
    assert rm[RUN_METADATA_KEY_PROMPT_COMPOSITION] is result.prompt_composition


def test_execution_log_prompt_hash_matches_request_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Redacted execution log carries the same prompt hash as full request metadata (default: no full text)."""
    captured: dict[str, Any] = {}

    def _handler(request: LLMRequest, settings: Any) -> LLMResponse:
        del settings
        captured["request"] = request
        return llm_response_success(parsed_json={"total_entities_detected": 0, "entities": []})

    executor = TestLLMExecutor(handler=_handler)
    patch_hybrid_resolve_llm_executor(monkeypatch, executor)
    context = _video_context(tmp_path)
    HybridGlobalAnalysisStrategy().analyze(
        context=context,
        frames_nd=[np.zeros((8, 8, 3), dtype=np.uint8)],
        frame_paths=[Path("/tmp/f.jpg")],
        frame_refs=["f0"],
        metadata={"frame_count": 1},
    )
    req = captured["request"]
    ph = req.metadata[LLM_METADATA_KEY_PROMPT_COMPOSITION]["prompt_hash"]
    prepared = next(
        c for c in context.execution_log.info.call_args_list if c.args[1] == "Analysis request prepared"
    )
    payload = prepared.kwargs["payload"]
    assert payload["prompt_composition"]["prompt_hash"] == ph
    assert payload["prompt_text_sha256"] == ph


def test_analysis_stage_forwards_prompt_composition_reference() -> None:
    """AnalysisStage must not copy prompt_composition; pipeline persistence relies on object identity."""
    shared: dict = {"prompt_hash": "x", "schema_version": "prompt_composition_v1"}
    mock_provider = MagicMock()
    mock_provider.analyze.return_value = AnalysisResult(
        parsed_json={"total_entities_detected": 0, "entities": []},
        provider_name=HARNESS_RESPONSE_PROVIDER,
        prompt_composition=shared,
    )
    context = MagicMock(spec=RunContext)
    context.job_id = "j1"
    acquired = AcquiredFrames(
        frames_nd=[np.zeros((4, 4, 3), dtype=np.uint8)],
        frame_paths=[Path("/tmp/f0.jpg")],
        metadata={"frame_count": 1},
        frame_refs=["f0"],
    )
    out = AnalysisStage(mock_provider).run(context, acquired)
    assert isinstance(out, AnalysisStageResult)
    assert out.prompt_composition is shared
