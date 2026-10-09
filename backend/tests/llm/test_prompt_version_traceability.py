"""Phase 7 — optional logical ``prompt_version`` in prompt composition (no prompt text change)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from src.llm.prompt_composer.prompt_traceability import (
    COMPOSITION_STEP_COMPOSE_HYBRID_BASE,
    build_prompt_composition_dict,
    validate_prompt_composition_dict,
)
from src.pipeline.context.run_context import RunContext
from src.pipeline.run_metadata import RUN_METADATA_KEY_PROMPT_COMPOSITION, build_run_metadata
from src.pipeline.services.hybrid_analysis_prompt import (
    build_hybrid_analysis_prompt_with_traceability,
)


def _video_run_context(
    *, settings_prompt_version: str | None = None, job_prompt_version: str | None = None
) -> RunContext:
    job_input = MagicMock()
    job_input.input_type = "video"
    settings = MagicMock()
    settings.hybrid_prompt = "global_v21"
    settings.prompt_version = settings_prompt_version
    return RunContext(
        job_id="j",
        run_id="r",
        workspace_path=Path("/tmp"),
        run_dir=Path("/tmp/j/r"),
        job_input=job_input,
        settings=settings,
        logger=MagicMock(),
        job_prompt_version=job_prompt_version,
    )


def test_prompt_version_from_settings_when_no_job_version() -> None:
    _, meta = build_hybrid_analysis_prompt_with_traceability(
        _video_run_context(settings_prompt_version="v1")
    )
    assert meta.get("prompt_version") == "v1"
    assert validate_prompt_composition_dict(meta) == []


def test_job_prompt_version_overrides_settings() -> None:
    _, meta = build_hybrid_analysis_prompt_with_traceability(
        _video_run_context(settings_prompt_version="from-settings", job_prompt_version="from-job")
    )
    assert meta.get("prompt_version") == "from-job"


def test_prompt_version_none_when_unset() -> None:
    _, meta = build_hybrid_analysis_prompt_with_traceability(_video_run_context())
    assert meta.get("prompt_version") is None
    assert validate_prompt_composition_dict(meta) == []


def test_prompt_version_does_not_change_prompt_hash_or_text() -> None:
    ctx_a = _video_run_context()
    ctx_b = _video_run_context(settings_prompt_version="experiment-2026-04-10")
    text_a, meta_a = build_hybrid_analysis_prompt_with_traceability(ctx_a)
    text_b, meta_b = build_hybrid_analysis_prompt_with_traceability(ctx_b)
    assert text_a == text_b
    assert meta_a["prompt_hash"] == meta_b["prompt_hash"]
    assert meta_a["base_prompt_hash"] == meta_b["base_prompt_hash"]
    assert meta_b["prompt_version"] == "experiment-2026-04-10"
    assert meta_a.get("prompt_version") is None


def test_prompt_version_does_not_change_resolved_profile_name() -> None:
    """Semantic invariant: version label is orthogonal to which profile was resolved."""
    ctx_a = _video_run_context()
    ctx_b = _video_run_context(settings_prompt_version="label-only")
    _, meta_a = build_hybrid_analysis_prompt_with_traceability(ctx_a)
    _, meta_b = build_hybrid_analysis_prompt_with_traceability(ctx_b)
    assert meta_a["profile_name"] == meta_b["profile_name"]


def test_composition_carries_job_prompt_key_profile_and_prompt_version_together() -> None:
    """profile_name (resolved body), job_prompt_key, and Phase 7 prompt_version coexist in metadata."""
    job_input = MagicMock()
    job_input.input_type = "video"
    settings = MagicMock()
    settings.hybrid_prompt = "global_v21"
    settings.prompt_version = "from-settings-unused"
    ctx = RunContext(
        job_id="j",
        run_id="r",
        workspace_path=Path("/tmp"),
        run_dir=Path("/tmp/j/r"),
        job_input=job_input,
        settings=settings,
        logger=MagicMock(),
        job_prompt_key="global_v21_b",
        job_prompt_version="job-trace-1",
    )
    _, meta = build_hybrid_analysis_prompt_with_traceability(ctx)
    assert meta["profile_name"] == "global_v22"
    assert meta["job_prompt_key"] == "global_v21_b"
    assert meta["settings_hybrid_prompt_key"] == "global_v21"
    assert meta["prompt_version"] == "job-trace-1"


def test_run_metadata_nested_prompt_composition_preserves_prompt_version() -> None:
    """Phase 7 label is visible under run_metadata['prompt_composition'] (same object, no copy)."""
    pc = build_prompt_composition_dict(
        profile_name="global_v21",
        pipeline_provider_key="gemini",
        base_prompt_text="x",
        final_prompt_text="x",
        enrichments_applied=[],
        composition_steps=[{"step": COMPOSITION_STEP_COMPOSE_HYBRID_BASE}],
        job_prompt_key="global_v21",
        settings_hybrid_prompt_key="global_v21",
        prompt_version="release-candidate-1",
    )
    rm = build_run_metadata(None, None, prompt_composition=pc)
    nested = rm[RUN_METADATA_KEY_PROMPT_COMPOSITION]
    assert nested is pc
    assert nested.get("prompt_version") == "release-candidate-1"


def test_run_metadata_prompt_composition_backward_compatible_without_prompt_version_key() -> None:
    """Older blobs may omit prompt_version; run_metadata still accepts the dict."""
    pc = build_prompt_composition_dict(
        profile_name="global_v21",
        pipeline_provider_key="openai",
        base_prompt_text="a",
        final_prompt_text="a",
        enrichments_applied=[],
        composition_steps=[],
        job_prompt_key=None,
        settings_hybrid_prompt_key="global_v21",
        prompt_version=None,
    )
    legacy = {k: v for k, v in pc.items() if k != "prompt_version"}
    assert "prompt_version" not in legacy
    rm = build_run_metadata(None, None, prompt_composition=legacy)
    assert "prompt_version" not in rm[RUN_METADATA_KEY_PROMPT_COMPOSITION]


def test_validate_accepts_composition_without_prompt_version_key() -> None:
    """Backward compatibility: older persisted blobs may omit ``prompt_version``."""
    _, meta = build_hybrid_analysis_prompt_with_traceability(_video_run_context())
    legacy = {k: v for k, v in meta.items() if k != "prompt_version"}
    assert "prompt_version" not in legacy
    # Should still validate hashes and required structural fields
    assert validate_prompt_composition_dict(legacy) == []
