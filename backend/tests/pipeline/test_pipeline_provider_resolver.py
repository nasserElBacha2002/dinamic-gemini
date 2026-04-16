"""Phase 3 / 8 — :mod:`src.pipeline.services.pipeline_provider_resolver` behavior."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.pipeline.providers.registry import UnknownPipelineProviderError
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


def test_unknown_provider_raises() -> None:
    with pytest.raises(UnknownPipelineProviderError):
        resolve_llm_executor_for_context("not_a_real_provider_ever", MagicMock())
