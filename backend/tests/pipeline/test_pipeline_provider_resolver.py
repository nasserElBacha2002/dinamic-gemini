"""Phase 3 / 8 — :mod:`src.pipeline.services.pipeline_provider_resolver` behavior."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.llm.errors import LLMProviderError
from src.llm.provider_error_taxonomy import PROVIDER_INCOMPATIBLE_WITH_JOB
from src.pipeline.services.pipeline_provider_resolver import (
    PipelineProviderResolver,
    resolve_llm_executor_for_context,
)


def test_resolve_llm_executor_for_context_prefers_explicit_job_provider() -> None:
    settings = MagicMock()
    settings.llm_provider = "gemini"
    _, key = resolve_llm_executor_for_context("openai", settings)
    assert key == "openai"


def test_resolve_llm_executor_for_context_falls_back_to_settings_llm_provider() -> None:
    settings = MagicMock()
    settings.llm_provider = "claude"
    _, key = resolve_llm_executor_for_context(None, settings)
    assert key == "claude"


def test_pipeline_provider_resolver_effective_provider_key() -> None:
    settings = MagicMock()
    settings.llm_provider = "openai"
    assert PipelineProviderResolver.effective_provider_key(None, settings) == "openai"
    assert PipelineProviderResolver.effective_provider_key("  Gemini  ", settings) == "gemini"


def test_explicit_inactive_provider_raises_contract_error() -> None:
    with pytest.raises(LLMProviderError) as exc:
        resolve_llm_executor_for_context("deepseek", MagicMock())
    assert exc.value.canonical_code == PROVIDER_INCOMPATIBLE_WITH_JOB


def test_unknown_provider_raises_contract_error() -> None:
    with pytest.raises(LLMProviderError) as exc:
        resolve_llm_executor_for_context("not_a_real_provider_ever", MagicMock())
    assert exc.value.canonical_code == PROVIDER_INCOMPATIBLE_WITH_JOB


def test_resolve_for_run_exposes_requested_provider_key() -> None:
    settings = MagicMock()
    settings.llm_provider = "gemini"
    resolved = PipelineProviderResolver.resolve_for_run(
        pipeline_provider_name="openai",
        settings=settings,
    )
    assert resolved.normalized_provider_key == "openai"
    assert resolved.requested_provider_key == "openai"
