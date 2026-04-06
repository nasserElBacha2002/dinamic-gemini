"""Tests for ``normalize_pipeline_provider_key`` (no LLM adapter imports)."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.pipeline.provider_keys import normalize_pipeline_provider_key


def test_normalize_prefers_explicit_provider_name_over_settings() -> None:
    settings = MagicMock()
    settings.llm_provider = "fake"
    assert normalize_pipeline_provider_key("gemini", settings) == "gemini"


def test_normalize_falls_back_to_settings_llm_provider() -> None:
    settings = MagicMock()
    settings.llm_provider = "fake"
    assert normalize_pipeline_provider_key(None, settings) == "fake"
