"""Unit tests for ``effective_production_processing_keys``."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.application.services.production_inventory_processing import (
    effective_production_processing_keys,
)
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus
from src.llm.prompt_composer.hybrid_assembly import DEFAULT_HYBRID_PROMPT_PROFILE

_NOW = datetime(2026, 1, 2, tzinfo=timezone.utc)


def _settings(**kwargs: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "llm_provider": "gemini",
        "gemini_api_key": "gk",
        "openai_api_key": "",
        "anthropic_api_key": "",
        "deepseek_api_key": "",
        "gemini_model_name": "gemini-snap",
        "openai_model": "gpt-prod",
        "anthropic_model": "claude-prod",
        "processing_gemini_models": "gemini-snap",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _inv(
    *,
    primary_provider_name: str | None = "gemini",
    primary_model_name: str | None = "gemini-snap",
    primary_prompt_key: str | None = "db-prompt",
) -> Inventory:
    return Inventory(
        id="inv-prod",
        name="n",
        status=InventoryStatus.DRAFT,
        created_at=_NOW,
        updated_at=_NOW,
        processing_mode=InventoryProcessingMode.PRODUCTION,
        primary_provider_name=primary_provider_name,
        primary_model_name=primary_model_name,
        primary_prompt_key=primary_prompt_key,
        primary_prompt_version=None,
    )


def test_full_snapshot_uses_inventory_provider_and_production_default_model() -> None:
    p, m, pk = effective_production_processing_keys(_inv(), _settings())
    assert (p, m, pk) == ("gemini", "gemini-snap", DEFAULT_HYBRID_PROMPT_PROFILE)


def test_partial_snapshot_uses_env_default_provider() -> None:
    s = _settings(llm_provider="openai", openai_api_key="ok")
    inv = _inv(primary_provider_name=None, primary_model_name=None)
    p, m, pk = effective_production_processing_keys(inv, s)
    assert (p, m, pk) == ("openai", "gpt-prod", DEFAULT_HYBRID_PROMPT_PROFILE)
