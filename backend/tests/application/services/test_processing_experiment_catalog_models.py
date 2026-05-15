"""Env-driven model lists and default model resolution for processing experiments."""

from __future__ import annotations

import os
from unittest.mock import patch

from src.application.services.processing_experiment_catalog import (
    default_model_for_provider,
    default_prompt_key,
    is_valid_prompt_key,
    models_for_provider,
    prompt_profile_catalog,
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


def test_models_for_provider_deepseek_uses_processing_deepseek_models_env() -> None:
    env = {
        "PROCESSING_DEEPSEEK_MODELS": "ds-one,ds-two",
    }
    with patch.dict(os.environ, env, clear=True):
        s = Settings()
    assert [m for m, _ in models_for_provider("deepseek", s)] == ["ds-one", "ds-two"]


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


def test_default_model_when_deepseek_model_not_in_processing_list_uses_first_offered() -> None:
    s = Settings()
    s.processing_deepseek_models = "custom-d1,custom-d2"
    s.deepseek_model = "deepseek-chat"
    assert default_model_for_provider("deepseek", s) == "custom-d1"


def test_prompt_profile_catalog_includes_global_v22() -> None:
    keys = [k for k, _lab, _desc in prompt_profile_catalog()]
    assert keys == ["global_v21", "global_v21_b", "global_v22"]


def test_is_valid_prompt_key_accepts_global_v22() -> None:
    s = Settings()
    assert is_valid_prompt_key("global_v22", s) is True
    assert is_valid_prompt_key("global_v21", s) is True


def test_default_prompt_key_empty_hybrid_prompt_uses_global_v22() -> None:
    s = Settings()
    s.hybrid_prompt = ""
    assert default_prompt_key(s) == "global_v22"
