"""v3.2.4 Phase 4 — Provider-side consumption of analysis context (visual references).

Tests: capability behavior, Gemini adapter with/without refs, non-capable provider metadata.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.pipeline.adapters.gemini_analysis_provider import GeminiAnalysisProvider
from src.pipeline.context.run_context import RunContext
from src.pipeline.ports.analysis_provider import (
    PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT,
    PROVIDER_METADATA_KEY_VISUAL_REFERENCES_AVAILABLE,
    PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED,
    ProviderCapabilities,
)


def _run_context(metadata: dict | None = None, settings_output_dir: str = "/tmp/out") -> RunContext:
    job_input = MagicMock()
    job_input.metadata = metadata
    job_input.input_type = "video"
    settings = MagicMock()
    settings.llm_provider = "fake"
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


def test_gemini_provider_capabilities_default() -> None:
    """GeminiAnalysisProvider declares supports_visual_reference_context=True by default."""
    provider = GeminiAnalysisProvider()
    caps = provider.get_capabilities()
    assert isinstance(caps, ProviderCapabilities)
    assert caps.supports_visual_reference_context is True


def test_gemini_provider_capabilities_disabled() -> None:
    """GeminiAnalysisProvider(supports_visual_reference_context=False) declares no ref support."""
    provider = GeminiAnalysisProvider(supports_visual_reference_context=False)
    caps = provider.get_capabilities()
    assert caps.supports_visual_reference_context is False


def test_gemini_provider_no_analysis_context_returns_metadata() -> None:
    """When job_input.metadata has no analysis_context, result has available=False, consumed=False."""
    context = _run_context(metadata={})
    provider = GeminiAnalysisProvider()
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


def test_gemini_provider_empty_visual_references_returns_metadata() -> None:
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
    provider = GeminiAnalysisProvider()
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


def test_gemini_provider_instruction_only_no_refs() -> None:
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
    provider = GeminiAnalysisProvider()
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


def test_gemini_provider_non_capable_with_refs_in_context() -> None:
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
    provider = GeminiAnalysisProvider(supports_visual_reference_context=False)
    result = provider.analyze(
        context=context,
        frames_nd=[np.zeros((64, 64, 3), dtype=np.uint8)],
        frame_paths=[Path("/tmp/f0.jpg")],
        frame_refs=["f0"],
        metadata={"frame_count": 1},
    )
    assert result.provider_metadata[PROVIDER_METADATA_KEY_VISUAL_REFERENCES_AVAILABLE] is True
    assert result.provider_metadata[PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED] is False
    # Plan: non-capable reports visual_reference_count=0 (or omit)
    assert result.provider_metadata[PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT] == 0


def test_gemini_provider_capable_with_refs_missing_files() -> None:
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
    provider = GeminiAnalysisProvider()
    result = provider.analyze(
        context=context,
        frames_nd=[np.zeros((64, 64, 3), dtype=np.uint8)],
        frame_paths=[Path("/tmp/f0.jpg")],
        frame_refs=["f0"],
        metadata={"frame_count": 1},
    )
    assert result.provider_metadata[PROVIDER_METADATA_KEY_VISUAL_REFERENCES_AVAILABLE] is True
    assert result.provider_metadata[PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED] is False
    # No images loaded -> consumed=False -> count=0 per metadata contract
    assert result.provider_metadata[PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT] == 0


def test_gemini_provider_capable_with_refs_and_existing_file(tmp_path: Path) -> None:
    """When capable and ref has resolved_path to existing file, provider loads it and reports consumed=True, count=1."""
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
    provider = GeminiAnalysisProvider()
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
    assert "total_entities_detected" in result.parsed_json
    assert "entities" in result.parsed_json
