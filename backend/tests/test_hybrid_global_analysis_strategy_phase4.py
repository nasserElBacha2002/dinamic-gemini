"""v3.2.4 Phase 4 — Provider-side consumption of analysis context (visual references).

Tests: ``HybridGlobalAnalysisStrategy`` capabilities, reference loading, execution log payloads.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.llm.types import LLMResponse
from src.pipeline.adapters.hybrid_global_analysis_strategy import HybridGlobalAnalysisStrategy
from src.pipeline.context.run_context import RunContext
from src.pipeline.execution_log import ExecutionLogWriter, read_execution_log_file
from src.pipeline.ports.analysis_provider import (
    PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT,
    PROVIDER_METADATA_KEY_VISUAL_REFERENCE_IDS,
    PROVIDER_METADATA_KEY_VISUAL_REFERENCES_AVAILABLE,
    PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED,
    ProviderCapabilities,
)
from tests.support.llm_executor_harness import HARNESS_LOGICAL_PROVIDER_KEY


@pytest.fixture(autouse=True)
def _patch_default_hybrid_llm_executor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Phase 2: default tests use ``TestLLMExecutor`` (vendor-agnostic resolved key)."""
    from tests.support.llm_executor_harness import TestLLMExecutor, patch_hybrid_resolve_llm_executor

    patch_hybrid_resolve_llm_executor(monkeypatch, TestLLMExecutor())


def _run_context(metadata: dict | None = None, settings_output_dir: str = "/tmp/out") -> RunContext:
    job_input = MagicMock()
    job_input.metadata = metadata
    job_input.input_type = "video"
    settings = MagicMock()
    settings.llm_provider = "openai"
    settings.fake_llm_fixture_path = None
    settings.output_dir = settings_output_dir
    settings.hybrid_prompt = "global_v21"
    return RunContext(
        job_id="j1",
        run_id="r1",
        workspace_path=Path("/tmp"),
        run_dir=Path("/tmp/j1/r1"),
        job_input=job_input,
        settings=settings,
        logger=MagicMock(),
    )


def test_hybrid_strategy_capabilities_default() -> None:
    """Default strategy declares supports_visual_reference_context=True."""
    provider = HybridGlobalAnalysisStrategy()
    caps = provider.get_capabilities()
    assert isinstance(caps, ProviderCapabilities)
    assert caps.supports_visual_reference_context is True


def test_hybrid_strategy_capabilities_disabled() -> None:
    """supports_visual_reference_context=False disables ref attachment to the LLM request."""
    provider = HybridGlobalAnalysisStrategy(supports_visual_reference_context=False)
    caps = provider.get_capabilities()
    assert caps.supports_visual_reference_context is False


def test_hybrid_strategy_no_analysis_context_returns_metadata() -> None:
    """When job_input.metadata has no analysis_context, result has available=False, consumed=False."""
    context = _run_context(metadata={})
    provider = HybridGlobalAnalysisStrategy()
    result = provider.analyze(
        context=context,
        frames_nd=[np.zeros((64, 64, 3), dtype=np.uint8)],
        frame_paths=[Path("/tmp/f0.jpg")],
        frame_refs=["f0"],
        metadata={"frame_count": 1},
    )
    assert result.provider_metadata is not None
    assert result.provider_metadata[PROVIDER_METADATA_KEY_VISUAL_REFERENCES_AVAILABLE] is False
    assert result.provider_metadata[PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED] is False
    assert result.provider_metadata[PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT] == 0


def test_hybrid_strategy_empty_visual_references_returns_metadata() -> None:
    """When analysis_context has empty visual_references, metadata has available=False, consumed=False."""
    context = _run_context(
        metadata={
            "analysis_context": {
                "primary_evidence": [],
                "visual_references": [],
                "instructions": [],
            },
        },
    )
    provider = HybridGlobalAnalysisStrategy()
    result = provider.analyze(
        context=context,
        frames_nd=[np.zeros((64, 64, 3), dtype=np.uint8)],
        frame_paths=[Path("/tmp/f0.jpg")],
        frame_refs=["f0"],
        metadata={"frame_count": 1},
    )
    assert result.provider_metadata[PROVIDER_METADATA_KEY_VISUAL_REFERENCES_AVAILABLE] is False
    assert result.provider_metadata[PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED] is False
    assert result.provider_metadata[PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT] == 0


def test_hybrid_strategy_instruction_only_no_refs() -> None:
    """Context has instructions but no refs: instruction enriches prompt; metadata reports no refs consumed."""
    context = _run_context(
        metadata={
            "analysis_context": {
                "primary_evidence": [],
                "visual_references": [],
                "instructions": ["Treat these as reference context."],
            },
        },
    )
    provider = HybridGlobalAnalysisStrategy()
    result = provider.analyze(
        context=context,
        frames_nd=[np.zeros((64, 64, 3), dtype=np.uint8)],
        frame_paths=[Path("/tmp/f0.jpg")],
        frame_refs=["f0"],
        metadata={"frame_count": 1},
    )
    assert result.provider_metadata[PROVIDER_METADATA_KEY_VISUAL_REFERENCES_AVAILABLE] is False
    assert result.provider_metadata[PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED] is False
    assert result.provider_metadata[PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT] == 0
    assert "total_entities_detected" in result.parsed_json


def test_hybrid_strategy_non_capable_with_refs_in_context() -> None:
    """When supports_visual_reference_context=False but context has refs: available=True, consumed=False, count=0."""
    context = _run_context(
        metadata={
            "analysis_context": {
                "primary_evidence": [],
                "visual_references": [
                    {"reference_id": "r1", "source_path": "inventories/inv1/visual_references/r1.jpg", "mime_type": "image/jpeg"},
                ],
                "instructions": ["Use refs as context."],
            },
        },
    )
    provider = HybridGlobalAnalysisStrategy(supports_visual_reference_context=False)
    result = provider.analyze(
        context=context,
        frames_nd=[np.zeros((64, 64, 3), dtype=np.uint8)],
        frame_paths=[Path("/tmp/f0.jpg")],
        frame_refs=["f0"],
        metadata={"frame_count": 1},
    )
    assert result.provider_metadata[PROVIDER_METADATA_KEY_VISUAL_REFERENCES_AVAILABLE] is True
    assert result.provider_metadata[PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED] is False
    assert result.provider_metadata[PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT] == 0


def test_hybrid_strategy_capable_with_refs_missing_files() -> None:
    """When capable and context has refs with resolved_path but file missing: available=True, consumed=False, count=0."""
    context = _run_context(
        metadata={
            "analysis_context": {
                "primary_evidence": [],
                "visual_references": [
                    {
                        "reference_id": "r1",
                        "source_path": "inventories/inv1/visual_references/nonexistent.jpg",
                        "mime_type": "image/jpeg",
                        "resolved_path": "/nonexistent/v3_uploads/inventories/inv1/visual_references/nonexistent.jpg",
                    },
                ],
                "instructions": ["Use refs as context."],
            },
        },
    )
    provider = HybridGlobalAnalysisStrategy()
    result = provider.analyze(
        context=context,
        frames_nd=[np.zeros((64, 64, 3), dtype=np.uint8)],
        frame_paths=[Path("/tmp/f0.jpg")],
        frame_refs=["f0"],
        metadata={"frame_count": 1},
    )
    assert result.provider_metadata[PROVIDER_METADATA_KEY_VISUAL_REFERENCES_AVAILABLE] is True
    assert result.provider_metadata[PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED] is False
    assert result.provider_metadata[PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT] == 0


def test_hybrid_strategy_capable_with_refs_and_existing_file(tmp_path: Path) -> None:
    """When capable and ref has resolved_path to existing file, strategy loads it and reports consumed=True, count=1."""
    import cv2

    ref_full = tmp_path / "ref1.jpg"
    ref_full.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ref_full), np.zeros((32, 32, 3), dtype=np.uint8))

    context = _run_context(
        metadata={
            "analysis_context": {
                "primary_evidence": [],
                "visual_references": [
                    {
                        "reference_id": "r1",
                        "source_path": "inventories/inv1/visual_references/r1.jpg",
                        "mime_type": "image/jpeg",
                        "resolved_path": str(ref_full),
                    },
                ],
                "instructions": ["Use refs as context."],
            },
        },
    )
    provider = HybridGlobalAnalysisStrategy()
    result = provider.analyze(
        context=context,
        frames_nd=[np.zeros((64, 64, 3), dtype=np.uint8)],
        frame_paths=[Path("/tmp/f0.jpg")],
        frame_refs=["f0"],
        metadata={"frame_count": 1},
    )
    assert result.provider_metadata[PROVIDER_METADATA_KEY_VISUAL_REFERENCES_AVAILABLE] is True
    assert result.provider_metadata[PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED] is True
    assert result.provider_metadata[PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT] == 1
    assert result.provider_metadata[PROVIDER_METADATA_KEY_VISUAL_REFERENCE_IDS] == ["r1"]
    assert "total_entities_detected" in result.parsed_json
    assert "entities" in result.parsed_json


def test_hybrid_strategy_logs_exact_prompt_and_attachments(tmp_path: Path) -> None:
    import cv2

    ref_full = tmp_path / "reference-image.jpg"
    ref_full.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ref_full), np.zeros((24, 24, 3), dtype=np.uint8))

    context = _run_context(
        metadata={
            "analysis_context": {
                "primary_evidence": [],
                "visual_references": [
                    {
                        "reference_id": "ref-1",
                        "source_path": "inventories/inv-1/visual_references/reference-image.jpg",
                        "mime_type": "image/jpeg",
                        "resolved_path": str(ref_full),
                    },
                ],
                "instructions": ["Use refs as context."],
            },
        },
    )
    context.execution_log = MagicMock()

    provider = HybridGlobalAnalysisStrategy()
    provider.analyze(
        context=context,
        frames_nd=[np.zeros((64, 64, 3), dtype=np.uint8)],
        frame_paths=[Path("/tmp/input/photo-01.jpg")],
        frame_refs=["img_001"],
        metadata={"frame_count": 1},
    )

    info_calls = context.execution_log.info.call_args_list
    prepared_call = next((call for call in info_calls if call.args[1] == "Analysis request prepared"), None)
    assert prepared_call is not None
    payload = prepared_call.kwargs["payload"]
    assert payload["event_type"] == "analysis_request"
    assert payload["pipeline_provider"] == HARNESS_LOGICAL_PROVIDER_KEY
    assert "Entity types:" in payload["prompt_text"]
    assert "PALLET" in payload["prompt_text"]
    assert "total_entities_detected" in payload["prompt_text"]
    assert payload["attachment_summary"]["primary_evidence_count"] == 1
    assert payload["attachment_summary"]["visual_reference_count"] == 1
    assert payload["primary_evidence_attachments"][0]["frame_ref"] == "img_001"
    assert payload["primary_evidence_attachments"][0]["filename"] == "photo-01.jpg"
    assert "path" not in payload["primary_evidence_attachments"][0]
    assert payload["visual_reference_attachments"][0]["reference_id"] == "ref-1"
    assert payload["visual_reference_attachments"][0]["filename"] == "reference-image.jpg"
    assert payload["visual_reference_attachments"][0]["resolved"] is True
    assert "source_path" not in payload["visual_reference_attachments"][0]
    assert "resolved_path" not in payload["visual_reference_attachments"][0]


def test_hybrid_strategy_logs_unresolved_visual_reference_without_counting_it_as_consumed() -> None:
    context = _run_context(
        metadata={
            "analysis_context": {
                "primary_evidence": [],
                "visual_references": [
                    {
                        "reference_id": "ref-1",
                        "source_path": "inventories/inv-1/visual_references/missing.jpg",
                        "mime_type": "image/jpeg",
                    },
                ],
                "instructions": ["Use refs as context."],
            },
        },
    )
    context.execution_log = MagicMock()

    provider = HybridGlobalAnalysisStrategy()
    result = provider.analyze(
        context=context,
        frames_nd=[np.zeros((64, 64, 3), dtype=np.uint8)],
        frame_paths=[Path("/tmp/input/photo-01.jpg")],
        frame_refs=["img_001"],
        metadata={"frame_count": 1},
    )

    prepared_call = next((call for call in context.execution_log.info.call_args_list if call.args[1] == "Analysis request prepared"), None)
    assert prepared_call is not None
    payload = prepared_call.kwargs["payload"]
    assert payload["attachment_summary"]["visual_reference_count"] == 0
    assert payload["visual_reference_attachments"][0]["reference_id"] == "ref-1"
    assert payload["visual_reference_attachments"][0]["resolved"] is False
    assert result.provider_metadata[PROVIDER_METADATA_KEY_VISUAL_REFERENCES_AVAILABLE] is True
    assert result.provider_metadata[PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED] is False
    assert result.provider_metadata[PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT] == 0
    assert result.provider_metadata[PROVIDER_METADATA_KEY_VISUAL_REFERENCE_IDS] == []


def test_hybrid_strategy_persists_structured_request_event_to_execution_log_file(tmp_path: Path) -> None:
    import cv2

    ref_full = tmp_path / "reference-image.jpg"
    ref_full.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ref_full), np.zeros((24, 24, 3), dtype=np.uint8))

    context = _run_context(
        metadata={
            "analysis_context": {
                "primary_evidence": [],
                "visual_references": [
                    {
                        "reference_id": "ref-1",
                        "source_path": "inventories/inv-1/visual_references/reference-image.jpg",
                        "mime_type": "image/jpeg",
                        "resolved_path": str(ref_full),
                    },
                ],
                "instructions": ["Use refs as context."],
            },
        },
        settings_output_dir=str(tmp_path),
    )
    run_dir = tmp_path / "job-1" / "run"
    context.run_dir = run_dir
    context.execution_log = ExecutionLogWriter(run_dir)

    provider = HybridGlobalAnalysisStrategy()
    provider.analyze(
        context=context,
        frames_nd=[np.zeros((64, 64, 3), dtype=np.uint8)],
        frame_paths=[Path("/tmp/input/photo-01.jpg")],
        frame_refs=["img_001"],
        metadata={"frame_count": 1},
    )

    events = read_execution_log_file(run_dir / "execution_log.jsonl")
    prepared_event = next((event for event in events if event.get("message") == "Analysis request prepared"), None)
    assert prepared_event is not None
    payload = prepared_event["payload"]
    assert payload["event_type"] == "analysis_request"
    assert payload["attachment_summary"]["total_count"] == 2
    assert payload["primary_evidence_attachments"][0]["filename"] == "photo-01.jpg"
    assert payload["visual_reference_attachments"][0]["reference_id"] == "ref-1"


def test_openai_job_model_name_passed_in_llm_request_metadata(tmp_path: Path) -> None:
    """Phase 5: job model id must reach OpenAI executor via request.metadata."""
    context = _run_context(metadata={}, settings_output_dir=str(tmp_path))
    context.pipeline_provider_name = "openai"
    context.job_model_name = "gpt-4o-mini"
    context.settings.openai_api_key = "sk-test"

    mock_executor = MagicMock()
    mock_executor.execute.return_value = LLMResponse(
        provider="openai",
        model="gpt-4o-mini",
        latency_ms=1,
        parsed_json={"total_entities_detected": 0, "entities": []},
    )

    with patch(
        "src.pipeline.adapters.hybrid_global_analysis_strategy.resolve_llm_executor_for_context",
        return_value=(mock_executor, "openai"),
    ):
        provider = HybridGlobalAnalysisStrategy()
        provider.analyze(
            context=context,
            frames_nd=[np.zeros((8, 8, 3), dtype=np.uint8)],
            frame_paths=[Path("/tmp/f0.jpg")],
            frame_refs=["f0"],
            metadata={"frame_count": 1},
        )

    req = mock_executor.execute.call_args[0][0]
    assert req.metadata.get("openai_model_name") == "gpt-4o-mini"
