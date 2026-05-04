"""Phase 4 — provider registry resolution and unknown-provider behavior."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.llm.anthropic_sdk_adapter import AnthropicSdkAdapter
from src.llm.deepseek_sdk_adapter import DeepSeekSdkAdapter
from src.llm.gemini_sdk_adapter import GeminiSdkAdapter
from src.llm.openai_sdk_adapter import OpenAiSdkAdapter
from src.pipeline.providers.registry import (
    UnknownPipelineProviderError,
    registered_pipeline_provider_keys,
    resolve_llm_executor,
)
from src.pipeline.services.pipeline_provider_resolver import resolve_llm_executor_for_context


def test_resolve_gemini_returns_sdk_adapter() -> None:
    settings = MagicMock()
    ex = resolve_llm_executor("gemini", settings)
    assert isinstance(ex, GeminiSdkAdapter)


def test_resolve_openai_returns_openai_sdk_adapter() -> None:
    settings = MagicMock()
    ex = resolve_llm_executor("openai", settings)
    assert isinstance(ex, OpenAiSdkAdapter)


def test_resolve_claude_returns_anthropic_sdk_adapter() -> None:
    settings = MagicMock()
    ex = resolve_llm_executor("claude", settings)
    assert isinstance(ex, AnthropicSdkAdapter)


def test_resolve_deepseek_returns_deepseek_sdk_adapter() -> None:
    settings = MagicMock()
    ex = resolve_llm_executor("deepseek", settings)
    assert isinstance(ex, DeepSeekSdkAdapter)


def test_resolve_unknown_raises() -> None:
    with pytest.raises(UnknownPipelineProviderError):
        resolve_llm_executor("unknown_vendor_xyz", MagicMock())


def test_registered_pipeline_provider_keys_includes_all_vendors() -> None:
    assert registered_pipeline_provider_keys() == frozenset(
        {"gemini", "openai", "claude", "deepseek"}
    )


def test_resolve_llm_executor_for_context_uses_job_provider_name() -> None:
    settings = MagicMock()
    settings.llm_provider = "gemini"
    ex, key = resolve_llm_executor_for_context("openai", settings)
    assert key == "openai"
    assert isinstance(ex, OpenAiSdkAdapter)
