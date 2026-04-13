"""Phase 5 — resolve_start_processing_request (provider, model, prompt)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.application.errors import (
    InvalidProcessingModelError,
    InvalidProcessingPromptKeyError,
    ProcessingProviderNotConfiguredError,
    UnknownProcessingProviderError,
)
from src.application.services.processing_provider_resolution import resolve_start_processing_request


def _settings(**overrides: object) -> MagicMock:
    s = MagicMock()
    s.llm_provider = "gemini"
    s.hybrid_prompt = "global_v21"
    s.gemini_api_key = "gk"
    s.openai_api_key = ""
    s.gemini_model_name = "gemini-2.0-flash-exp"
    s.openai_model = "gpt-4o"
    s.anthropic_api_key = ""
    s.anthropic_model = "claude-sonnet-4-20250514"
    s.processing_gemini_models = "gemini-2.0-flash-exp,gemini-1.5-flash"
    s.processing_openai_models = "gpt-4o,gpt-4o-mini"
    s.processing_claude_models = "claude-sonnet-4-20250514,claude-3-5-sonnet-20241022"
    s.deepseek_api_key = ""
    s.deepseek_model = "deepseek-chat"
    s.processing_deepseek_models = "deepseek-chat,deepseek-reasoner"
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def test_resolve_all_omitted_uses_defaults() -> None:
    s = _settings(gemini_api_key="")
    p, m, pk = resolve_start_processing_request(
        requested_provider_name=None,
        requested_model_name=None,
        requested_prompt_key=None,
        settings=s,
    )
    assert p == "gemini"
    assert m == "gemini-2.0-flash-exp"
    assert pk == "global_v21"


def test_resolve_explicit_gemini_model_and_prompt_b() -> None:
    s = _settings()
    p, m, pk = resolve_start_processing_request(
        requested_provider_name="gemini",
        requested_model_name="gemini-1.5-flash",
        requested_prompt_key="global_v21_b",
        settings=s,
    )
    assert p == "gemini"
    assert m == "gemini-1.5-flash"
    assert pk == "global_v21_b"


def test_resolve_invalid_model_raises() -> None:
    s = _settings()
    with pytest.raises(InvalidProcessingModelError):
        resolve_start_processing_request(
            requested_provider_name="gemini",
            requested_model_name="not-a-real-model",
            requested_prompt_key=None,
            settings=s,
        )


def test_resolve_invalid_prompt_raises() -> None:
    s = _settings()
    with pytest.raises(InvalidProcessingPromptKeyError):
        resolve_start_processing_request(
            requested_provider_name="gemini",
            requested_model_name=None,
            requested_prompt_key="not-a-prompt",
            settings=s,
        )


def test_resolve_unknown_provider_raises() -> None:
    s = _settings()
    with pytest.raises(UnknownProcessingProviderError):
        resolve_start_processing_request(
            requested_provider_name="acme",
            requested_model_name=None,
            requested_prompt_key=None,
            settings=s,
        )


def test_resolve_explicit_gemini_without_key_raises() -> None:
    s = _settings(gemini_api_key="")
    with pytest.raises(ProcessingProviderNotConfiguredError):
        resolve_start_processing_request(
            requested_provider_name="gemini",
            requested_model_name=None,
            requested_prompt_key=None,
            settings=s,
        )


def test_resolve_explicit_openai_uses_default_catalog_model() -> None:
    s = _settings(openai_api_key="sk-test", gemini_api_key="")
    p, m, pk = resolve_start_processing_request(
        requested_provider_name="openai",
        requested_model_name=None,
        requested_prompt_key=None,
        settings=s,
    )
    assert p == "openai"
    assert m == "gpt-4o"
    assert pk == "global_v21"


def test_resolve_explicit_claude_uses_default_catalog_model() -> None:
    s = _settings(anthropic_api_key="sk-ant-test", gemini_api_key="")
    p, m, pk = resolve_start_processing_request(
        requested_provider_name="claude",
        requested_model_name=None,
        requested_prompt_key=None,
        settings=s,
    )
    assert p == "claude"
    assert m == "claude-sonnet-4-20250514"
    assert pk == "global_v21"


def test_resolve_explicit_claude_without_key_raises() -> None:
    s = _settings(anthropic_api_key="", gemini_api_key="gk")
    with pytest.raises(ProcessingProviderNotConfiguredError):
        resolve_start_processing_request(
            requested_provider_name="claude",
            requested_model_name=None,
            requested_prompt_key=None,
            settings=s,
        )


def test_resolve_explicit_deepseek_uses_default_catalog_model() -> None:
    s = _settings(deepseek_api_key="sk-ds-test", gemini_api_key="")
    p, m, pk = resolve_start_processing_request(
        requested_provider_name="deepseek",
        requested_model_name=None,
        requested_prompt_key=None,
        settings=s,
    )
    assert p == "deepseek"
    assert m == "deepseek-chat"
    assert pk == "global_v21"


def test_resolve_explicit_deepseek_without_key_raises() -> None:
    s = _settings(deepseek_api_key="", gemini_api_key="gk")
    with pytest.raises(ProcessingProviderNotConfiguredError):
        resolve_start_processing_request(
            requested_provider_name="deepseek",
            requested_model_name=None,
            requested_prompt_key=None,
            settings=s,
        )
