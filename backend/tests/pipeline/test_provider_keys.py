"""Phase 5 — provider key resolution fail-closed behavior."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.pipeline.provider_keys import (
    InactivePipelineProviderKeyError,
    UnknownPipelineProviderKeyError,
    normalize_pipeline_provider_key,
    resolve_pipeline_provider_key,
)


def test_settings_default_deepseek_remaps_to_gemini_only_when_implicit() -> None:
    settings = SimpleNamespace(llm_provider="deepseek")
    resolved = resolve_pipeline_provider_key(None, settings)
    assert resolved.resolved_key == "gemini"
    assert resolved.requested_key is None
    assert not resolved.remapped


def test_explicit_deepseek_job_provider_fails_closed() -> None:
    settings = SimpleNamespace(llm_provider="gemini")
    with pytest.raises(InactivePipelineProviderKeyError):
        resolve_pipeline_provider_key("deepseek", settings)


def test_explicit_unknown_provider_fails_closed() -> None:
    settings = SimpleNamespace(llm_provider="gemini")
    with pytest.raises(UnknownPipelineProviderKeyError):
        resolve_pipeline_provider_key("not_a_real_provider_ever", settings)


def test_explicit_gemini_unchanged() -> None:
    settings = SimpleNamespace(llm_provider="openai")
    resolved = resolve_pipeline_provider_key("gemini", settings)
    assert resolved.resolved_key == "gemini"
    assert resolved.requested_key == "gemini"
    assert not resolved.remapped


def test_normalize_matches_resolve() -> None:
    settings = SimpleNamespace(llm_provider="gemini")
    assert normalize_pipeline_provider_key("openai", settings) == "openai"
