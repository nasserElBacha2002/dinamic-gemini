"""Pipeline provider key normalization — inactive legacy providers."""

from __future__ import annotations

from types import SimpleNamespace

from src.pipeline.provider_keys import normalize_pipeline_provider_key


def test_llm_provider_deepseek_remaps_to_gemini_for_new_runs() -> None:
    settings = SimpleNamespace(llm_provider="deepseek")
    assert normalize_pipeline_provider_key(None, settings) == "gemini"


def test_explicit_deepseek_job_provider_remaps_to_gemini() -> None:
    settings = SimpleNamespace(llm_provider="gemini")
    assert normalize_pipeline_provider_key("deepseek", settings) == "gemini"
