"""Phase 5 — visual inventory provider contract validation."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.application.errors import ProcessingProviderIncompatibleWithJobError
from src.application.services.provider_contract_validation import (
    resolve_and_validate_pipeline_provider_for_visual_job,
    validate_provider_for_visual_inventory_job,
    validate_provider_model_for_visual_inventory_job,
)


def test_deepseek_rejected_for_visual_inventory() -> None:
    with pytest.raises(ProcessingProviderIncompatibleWithJobError) as exc:
        validate_provider_for_visual_inventory_job("deepseek")
    assert exc.value.provider_key == "deepseek"
    assert "visual inventory" in str(exc.value).lower()


def test_unknown_provider_rejected_for_visual_inventory() -> None:
    with pytest.raises(ProcessingProviderIncompatibleWithJobError) as exc:
        validate_provider_for_visual_inventory_job("not_a_real_provider_ever")
    assert exc.value.provider_key == "not_a_real_provider_ever"


def test_gemini_accepted_for_visual_inventory() -> None:
    validate_provider_for_visual_inventory_job("gemini")
    validate_provider_model_for_visual_inventory_job("gemini", "gemini-2.0-flash")


def test_openai_text_only_model_rejected() -> None:
    with pytest.raises(ProcessingProviderIncompatibleWithJobError) as exc:
        validate_provider_model_for_visual_inventory_job("openai", "gpt-3.5-turbo")
    assert exc.value.provider_key == "openai"
    assert exc.value.model_name == "gpt-3.5-turbo"


def test_openai_vision_model_accepted() -> None:
    validate_provider_model_for_visual_inventory_job("openai", "gpt-4o")


def test_explicit_inactive_provider_fails_at_resolution() -> None:
    settings = SimpleNamespace(llm_provider="gemini")
    with pytest.raises(ProcessingProviderIncompatibleWithJobError) as exc:
        resolve_and_validate_pipeline_provider_for_visual_job("deepseek", settings)
    assert exc.value.provider_key == "deepseek"


def test_implicit_settings_deepseek_resolves_to_gemini_and_passes() -> None:
    settings = SimpleNamespace(llm_provider="deepseek")
    resolved = resolve_and_validate_pipeline_provider_for_visual_job(None, settings)
    assert resolved.resolved_key == "gemini"
    assert resolved.requested_key is None
    assert resolved.resolution_source == "settings_default_remapped"
