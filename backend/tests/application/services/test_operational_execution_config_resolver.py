"""Operational primary execution snapshot — production prompt policy vs env hints."""

from __future__ import annotations

from types import SimpleNamespace

from src.application.services.operational_execution_config_resolver import (
    OperationalExecutionConfigResolver,
)
from src.llm.prompt_composer.hybrid_assembly import DEFAULT_HYBRID_PROMPT_PROFILE


def _settings(**kwargs: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "llm_provider": "gemini",
        "gemini_api_key": "gk",
        "openai_api_key": "",
        "anthropic_api_key": "",
        "deepseek_api_key": "",
        "gemini_model_name": "gemini-snap",
        "processing_gemini_models": "gemini-snap",
        "hybrid_prompt": "global_v21",
        "prompt_version": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_operational_snapshot_pins_effective_aisle_profile_not_hybrid_prompt_env() -> None:
    snap = OperationalExecutionConfigResolver().resolve(_settings(hybrid_prompt="global_v21"))
    assert snap.prompt_key == DEFAULT_HYBRID_PROMPT_PROFILE
    assert snap.provider_name == "gemini"
    assert snap.model_name == "gemini-snap"


def test_operational_snapshot_ignores_prompt_version_env() -> None:
    snap = OperationalExecutionConfigResolver().resolve(
        _settings(prompt_version="experiment-A", hybrid_prompt="global_v21_b")
    )
    assert snap.prompt_version is None
    assert snap.prompt_key == DEFAULT_HYBRID_PROMPT_PROFILE
