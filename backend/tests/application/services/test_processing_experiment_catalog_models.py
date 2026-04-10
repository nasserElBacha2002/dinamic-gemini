"""Env-driven model lists and default model resolution for processing experiments."""

from __future__ import annotations

import os
from unittest.mock import patch

from src.application.services.processing_experiment_catalog import (
    default_model_for_provider,
    models_for_provider,
)
from src.config import Settings


def test_models_for_provider_gemini_uses_processing_gemini_models_env() -> None:
    env = {
        "PROCESSING_GEMINI_MODELS": "gemini-x,gemini-y",
    }
    with patch.dict(os.environ, env, clear=True):
        s = Settings()
    assert [m for m, _ in models_for_provider("gemini", s)] == ["gemini-x", "gemini-y"]


def test_models_for_provider_openai_uses_processing_openai_models_env() -> None:
    env = {
        "PROCESSING_OPENAI_MODELS": "gpt-one,gpt-two",
    }
    with patch.dict(os.environ, env, clear=True):
        s = Settings()
    assert [m for m, _ in models_for_provider("openai", s)] == ["gpt-one", "gpt-two"]


def test_models_for_provider_claude_uses_processing_claude_models_env() -> None:
    env = {
        "PROCESSING_CLAUDE_MODELS": "claude-one,claude-two",
    }
    with patch.dict(os.environ, env, clear=True):
        s = Settings()
    assert [m for m, _ in models_for_provider("claude", s)] == ["claude-one", "claude-two"]


def test_default_model_when_gemini_name_not_in_processing_list_uses_first_offered() -> None:
    s = Settings()
    s.processing_gemini_models = "only-a,only-b"
    s.gemini_model_name = "gemini-2.0-flash-exp"
    assert default_model_for_provider("gemini", s) == "only-a"


def test_default_model_when_openai_model_not_in_processing_list_uses_first_offered() -> None:
    s = Settings()
    s.processing_openai_models = "custom-a,custom-b"
    s.openai_model = "gpt-4o"
    assert default_model_for_provider("openai", s) == "custom-a"


def test_default_model_when_anthropic_model_not_in_processing_list_uses_first_offered() -> None:
    s = Settings()
    s.processing_claude_models = "custom-c1,custom-c2"
    s.anthropic_model = "claude-sonnet-4-20250514"
    assert default_model_for_provider("claude", s) == "custom-c1"
