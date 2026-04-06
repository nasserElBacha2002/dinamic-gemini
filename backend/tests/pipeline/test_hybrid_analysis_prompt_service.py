"""Provider-neutral prompt assembly for hybrid analysis."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from src.pipeline.context.run_context import RunContext
from src.pipeline.services.hybrid_analysis_prompt import (
    build_hybrid_analysis_prompt_text,
    resolve_analysis_context_for_run,
)


def test_build_hybrid_prompt_prefers_job_prompt_key() -> None:
    settings = MagicMock()
    settings.hybrid_prompt = "global_v21"
    job_input = MagicMock()
    job_input.input_type = "video"
    ctx = RunContext(
        job_id="j",
        run_id="r",
        workspace_path=Path("/tmp"),
        run_dir=Path("/tmp/j/r"),
        job_input=job_input,
        settings=settings,
        logger=MagicMock(),
        job_prompt_key="global_v21_b",
    )
    text = build_hybrid_analysis_prompt_text(ctx)
    assert "Conservative" in text or "conservative" in text.lower()
    assert "INSUFFICIENT_EVIDENCE" in text


def test_build_hybrid_prompt_uses_settings_hybrid_prompt_key() -> None:
    settings = MagicMock()
    settings.hybrid_prompt = "global_v21"
    job_input = MagicMock()
    job_input.input_type = "video"
    ctx = RunContext(
        job_id="j",
        run_id="r",
        workspace_path=Path("/tmp"),
        run_dir=Path("/tmp/j/r"),
        job_input=job_input,
        settings=settings,
        logger=MagicMock(),
    )
    text = build_hybrid_analysis_prompt_text(ctx)
    assert "warehouse" in text.lower() or "aisle" in text.lower() or len(text) > 50


def test_resolve_analysis_context_from_run_context_attribute() -> None:
    ac = MagicMock()
    ctx = RunContext(
        job_id="j",
        run_id="r",
        workspace_path=Path("/tmp"),
        run_dir=Path("/tmp/j/r"),
        job_input=MagicMock(),
        settings=MagicMock(),
        logger=MagicMock(),
        analysis_context=ac,
    )
    assert resolve_analysis_context_for_run(ctx) is ac
