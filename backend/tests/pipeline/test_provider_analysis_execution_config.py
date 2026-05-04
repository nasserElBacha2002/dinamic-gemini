"""Phase 4 — provider analysis execution config (strategy + ordered keys)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.env_settings.grouped_settings import LlmProviderSettings
from src.env_settings.pipeline_analysis_execution_strings import (
    STRATEGY_MULTI_SEQUENTIAL,
    normalize_pipeline_analysis_strategy_value,
    validate_pipeline_analysis_strategy_for_settings,
)
from src.pipeline.context.run_context import RunContext
from src.pipeline.services.provider_analysis_execution_config import (
    build_ordered_provider_keys,
    effective_analysis_execution_strategy,
    effective_extra_provider_keys,
)


def test_normalize_multi_fallback_alias() -> None:
    assert normalize_pipeline_analysis_strategy_value("multi_fallback") == STRATEGY_MULTI_SEQUENTIAL


def test_validate_strategy_accepts_multi_fallback() -> None:
    assert (
        validate_pipeline_analysis_strategy_for_settings("multi_fallback")
        == STRATEGY_MULTI_SEQUENTIAL
    )


def test_validate_strategy_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="pipeline_analysis_execution_strategy"):
        validate_pipeline_analysis_strategy_for_settings("quantum_llm")


def test_llm_provider_settings_normalizes_multi_fallback() -> None:
    s = LlmProviderSettings(pipeline_analysis_execution_strategy="multi_fallback")
    assert s.pipeline_analysis_execution_strategy == STRATEGY_MULTI_SEQUENTIAL


def test_effective_strategy_job_overrides_settings() -> None:
    settings = MagicMock()
    settings.pipeline_analysis_execution_strategy = "multi_parallel"
    ctx = RunContext(
        job_id="j",
        run_id="r",
        workspace_path=Path("/tmp"),
        run_dir=Path("/tmp/r"),
        job_input=MagicMock(),
        settings=settings,
        logger=MagicMock(),
        analysis_execution_strategy="single",
    )
    assert effective_analysis_execution_strategy(ctx, settings) == "single"


def test_effective_extra_keys_tuple_on_context_overrides_settings() -> None:
    settings = MagicMock()
    settings.pipeline_analysis_extra_provider_keys = "openai,claude"
    ctx = RunContext(
        job_id="j",
        run_id="r",
        workspace_path=Path("/tmp"),
        run_dir=Path("/tmp/r"),
        job_input=MagicMock(),
        settings=settings,
        logger=MagicMock(),
        analysis_extra_provider_keys=("deepseek",),
    )
    assert effective_extra_provider_keys(ctx, settings) == ["deepseek"]


def test_build_ordered_provider_keys_dedupes_and_skips_unknown() -> None:
    settings = MagicMock()
    settings.llm_provider = "gemini"
    settings.pipeline_analysis_extra_provider_keys = "openai, gemini , not_real"
    ctx = RunContext(
        job_id="j",
        run_id="r",
        workspace_path=Path("/tmp"),
        run_dir=Path("/tmp/r"),
        job_input=MagicMock(),
        settings=settings,
        logger=MagicMock(),
        pipeline_provider_name=None,
    )
    keys = build_ordered_provider_keys(ctx, settings)
    assert keys == ["gemini", "openai"]
