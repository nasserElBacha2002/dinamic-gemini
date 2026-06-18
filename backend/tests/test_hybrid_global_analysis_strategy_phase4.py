"""v3.2.4 Phase 4 — Provider-side consumption of analysis context (visual references).

Tests: ``HybridGlobalAnalysisStrategy`` capabilities, reference loading, execution log payloads.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.llm.prompt_composer.prompt_traceability import sha256_utf8
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
from src.pipeline.services.hybrid_analysis_prompt import (
    build_hybrid_analysis_prompt_with_traceability,
)
from src.pipeline.services.pipeline_provider_resolver import ResolvedPipelineExecution
from tests.support.llm_executor_harness import HARNESS_LOGICAL_PROVIDER_KEY


@pytest.fixture(autouse=True)
def _patch_default_hybrid_llm_executor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Phase 2: default tests use ``TestLLMExecutor`` (vendor-agnostic resolved key)."""
    from tests.support.llm_executor_harness import (
        TestLLMExecutor,
        patch_hybrid_resolve_llm_executor,
    )

    patch_hybrid_resolve_llm_executor(monkeypatch, TestLLMExecutor())


def _run_context(metadata: dict | None = None, settings_output_dir: str = "/tmp/out") -> RunContext:
    job_input = MagicMock()
    job_input.metadata = metadata
    job_input.input_type = "video"
    settings = MagicMock()
    settings.llm_provider = "openai"
    settings.output_dir = settings_output_dir
    settings.hybrid_prompt = "global_v21"
    settings.debug_log_full_analysis_prompt = False
    settings.execution_log_include_full_prompt = False
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
                    {
                        "reference_id": "r1",
                        "source_path": "inventories/inv1/visual_references/r1.jpg",
                        "mime_type": "image/jpeg",
                    },
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
    context.settings.debug_log_full_analysis_prompt = True

    provider = HybridGlobalAnalysisStrategy()
    provider.analyze(
        context=context,
        frames_nd=[np.zeros((64, 64, 3), dtype=np.uint8)],
        frame_paths=[Path("/tmp/input/photo-01.jpg")],
        frame_refs=["img_001"],
        metadata={"frame_count": 1},
    )

    info_calls = context.execution_log.info.call_args_list
    prepared_call = next(
        (call for call in info_calls if call.args[1] == "Analysis request prepared"), None
    )
    assert prepared_call is not None
    payload = prepared_call.kwargs["payload"]
    assert payload["event_type"] == "analysis_request"
    assert payload["pipeline_provider"] == HARNESS_LOGICAL_PROVIDER_KEY
    assert payload["prompt_composition"]["profile_name"]
    assert payload["prompt_composition"]["prompt_hash"]
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
    assert payload["prompt_text_sha256"]
    assert payload["prompt_text_len"] > 0


def test_hybrid_strategy_execution_log_includes_full_prompt_when_execution_log_flag_enabled(
    tmp_path: Path,
) -> None:
    """EXECUTION_LOG_INCLUDE_FULL_PROMPT adds prompt_text plus hash and length (no debug flag)."""
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
    context.settings.debug_log_full_analysis_prompt = False
    context.settings.execution_log_include_full_prompt = True

    provider = HybridGlobalAnalysisStrategy()
    provider.analyze(
        context=context,
        frames_nd=[np.zeros((64, 64, 3), dtype=np.uint8)],
        frame_paths=[Path("/tmp/input/photo-01.jpg")],
        frame_refs=["img_001"],
        metadata={"frame_count": 1},
    )

    prepared_call = next(
        (
            call
            for call in context.execution_log.info.call_args_list
            if call.args[1] == "Analysis request prepared"
        ),
        None,
    )
    assert prepared_call is not None
    payload = prepared_call.kwargs["payload"]
    assert "prompt_text" in payload
    assert "Entity types:" in payload["prompt_text"]
    assert payload["prompt_text_sha256"]
    assert payload["prompt_text_len"] > 0
    assert payload["prompt_text_sha256"] == sha256_utf8(payload["prompt_text"])


def test_hybrid_strategy_execution_log_hashes_prompt_when_debug_full_prompt_disabled(
    tmp_path: Path,
) -> None:
    """Phase 6: default execution_log omits full prompt_text; includes SHA-256 and length."""
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
    context.settings.debug_log_full_analysis_prompt = False

    provider = HybridGlobalAnalysisStrategy()
    provider.analyze(
        context=context,
        frames_nd=[np.zeros((64, 64, 3), dtype=np.uint8)],
        frame_paths=[Path("/tmp/input/photo-01.jpg")],
        frame_refs=["img_001"],
        metadata={"frame_count": 1},
    )

    prepared_call = next(
        (
            call
            for call in context.execution_log.info.call_args_list
            if call.args[1] == "Analysis request prepared"
        ),
        None,
    )
    assert prepared_call is not None
    payload = prepared_call.kwargs["payload"]
    assert "prompt_text" not in payload
    assert payload["prompt_text_sha256"]
    assert payload["prompt_text_len"] > 0
    pc = payload["prompt_composition"]
    assert pc["prompt_hash"] == payload["prompt_text_sha256"]
    prompt_text, comp = build_hybrid_analysis_prompt_with_traceability(context)
    assert sha256_utf8(prompt_text) == payload["prompt_text_sha256"]
    assert comp["prompt_hash"] == payload["prompt_text_sha256"]
    assert len(prompt_text) == payload["prompt_text_len"]


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

    prepared_call = next(
        (
            call
            for call in context.execution_log.info.call_args_list
            if call.args[1] == "Analysis request prepared"
        ),
        None,
    )
    assert prepared_call is not None
    payload = prepared_call.kwargs["payload"]
    assert payload["attachment_summary"]["visual_reference_count"] == 0
    assert payload["visual_reference_attachments"][0]["reference_id"] == "ref-1"
    assert payload["visual_reference_attachments"][0]["resolved"] is False
    assert result.provider_metadata[PROVIDER_METADATA_KEY_VISUAL_REFERENCES_AVAILABLE] is True
    assert result.provider_metadata[PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED] is False
    assert result.provider_metadata[PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT] == 0
    assert result.provider_metadata[PROVIDER_METADATA_KEY_VISUAL_REFERENCE_IDS] == []


def test_hybrid_strategy_persists_structured_request_event_to_execution_log_file(
    tmp_path: Path,
) -> None:
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
    prepared_event = next(
        (event for event in events if event.get("message") == "Analysis request prepared"), None
    )
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
        "src.pipeline.services.pipeline_provider_resolver.PipelineProviderResolver.resolve_for_run",
        return_value=ResolvedPipelineExecution(
            executor=mock_executor,
            normalized_provider_key="openai",
            requested_provider_key="openai",
            resolution_source="explicit_job_provider",
        ),
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
    pc = req.metadata.get("prompt_composition")
    assert isinstance(pc, dict)
    assert pc.get("resolved_llm_provider_key") == "openai"
    assert pc.get("model_name") == "gpt-4o-mini"
    assert pc.get("prompt_hash") == sha256_utf8(req.prompt)


def test_prepare_hybrid_llm_visual_bundle_instructions_only() -> None:
    """Phase 6 — visual bundle helper keeps instruction assembly separate from LLM request build."""
    from src.pipeline.adapters.hybrid_global_analysis_strategy import (
        _prepare_hybrid_llm_visual_bundle,
    )
    from src.pipeline.contracts.analysis_context import AnalysisContext

    ctx = AnalysisContext(
        primary_evidence=[],
        visual_references=[],
        instructions=["  a  ", "b"],
        metadata=None,
    )
    vb = _prepare_hybrid_llm_visual_bundle(
        supports_visual_reference_context=True,
        analysis_context=ctx,
        job_id="j1",
    )
    assert vb.context_instruction == "a  \nb"
    assert vb.context_images is None
    assert vb.consumed_count == 0


def test_prepare_hybrid_llm_visual_bundle_no_context() -> None:
    from src.pipeline.adapters.hybrid_global_analysis_strategy import (
        _prepare_hybrid_llm_visual_bundle,
    )

    vb = _prepare_hybrid_llm_visual_bundle(
        supports_visual_reference_context=True,
        analysis_context=None,
        job_id="j1",
    )
    assert vb.context_instruction is None
    assert vb.visual_reference_attachments == []


def test_prepare_hybrid_llm_visual_bundle_resolves_supplier_reference_files(
    tmp_path,
) -> None:
    """E5: resolved_path images load; attachment roles stay visual_reference (not primary_evidence)."""
    from PIL import Image

    from src.pipeline.adapters.hybrid_global_analysis_strategy import (
        _prepare_hybrid_llm_visual_bundle,
    )
    from src.pipeline.contracts.analysis_context import AnalysisContext, VisualReferenceContext
    from src.pipeline.services.analysis_visual_reference_prep import (
        build_primary_evidence_attachments,
    )

    p1 = tmp_path / "r1.png"
    p2 = tmp_path / "r2.png"
    Image.new("RGB", (8, 8), color=(1, 2, 3)).save(p1)
    Image.new("RGB", (8, 8), color=(4, 5, 6)).save(p2)
    ctx = AnalysisContext(
        primary_evidence=[],
        visual_references=[
            VisualReferenceContext(
                reference_id="id-1",
                source_path=str(p1),
                mime_type="image/png",
                role="supplier_reference",
                resolved_path=str(p1),
            ),
            VisualReferenceContext(
                reference_id="id-2",
                source_path=str(p2),
                mime_type="image/png",
                role="supplier_reference",
                resolved_path=str(p2),
            ),
        ],
        instructions=["Supplier reference images illustrate"],
        metadata=None,
    )
    vb = _prepare_hybrid_llm_visual_bundle(
        supports_visual_reference_context=True,
        analysis_context=ctx,
        job_id="job-e5",
    )
    assert vb.consumed_count == 2
    assert len(vb.visual_reference_attachments) == 2
    for a in vb.visual_reference_attachments:
        assert a["role"] == "visual_reference"
        assert a["role"] != "primary_evidence"
        assert a["resolved"] is True
    primary = build_primary_evidence_attachments(
        [tmp_path / "f0.jpg", tmp_path / "f1.jpg"],
        ["a", "b"],
    )
    assert len(primary) == 2
    assert all(x["role"] == "primary_evidence" for x in primary)
    assert len(primary) + vb.consumed_count == 4


def test_prepare_hybrid_llm_visual_bundle_missing_reference_file_still_emits_attachment(
    tmp_path,
) -> None:
    """E5: unreadable / missing file → resolved false; bundle still lists attachment for logs."""
    from src.pipeline.adapters.hybrid_global_analysis_strategy import (
        _prepare_hybrid_llm_visual_bundle,
    )
    from src.pipeline.contracts.analysis_context import AnalysisContext, VisualReferenceContext

    missing = tmp_path / "nope.png"
    ctx = AnalysisContext(
        primary_evidence=[],
        visual_references=[
            VisualReferenceContext(
                reference_id="gone",
                source_path="gone.png",
                mime_type="image/png",
                role="supplier_reference",
                resolved_path=str(missing),
            )
        ],
        instructions=["ctx"],
        metadata=None,
    )
    vb = _prepare_hybrid_llm_visual_bundle(
        supports_visual_reference_context=True,
        analysis_context=ctx,
        job_id="job-e5",
    )
    assert vb.consumed_count == 0
    assert len(vb.visual_reference_attachments) == 1
    att = vb.visual_reference_attachments[0]
    assert att["resolved"] is False
    assert att["role"] == "visual_reference"
