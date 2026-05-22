"""Production vs test provider/model availability catalog and resolution."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.application.errors import (
    DeprecatedProcessingProviderError,
    InvalidProcessingModelError,
    ProcessingProviderNotConfiguredError,
    UnknownProcessingProviderError,
)
from src.application.services.processing_provider_availability import (
    build_processing_provider_options_payload,
    effective_production_default_provider_key,
    production_provider_catalog,
    resolve_production_processing_keys,
)
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus

_NOW = datetime(2026, 3, 1, tzinfo=timezone.utc)


def _settings(**kwargs: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "llm_provider": "gemini",
        "gemini_api_key": "gk",
        "openai_api_key": "",
        "anthropic_api_key": "",
        "deepseek_api_key": "",
        "gemini_model_name": "gemini-prod-3.1",
        "openai_model": "gpt-prod",
        "anthropic_model": "claude-prod",
        "deepseek_model": "deepseek-chat",
        "processing_gemini_models": "gemini-a,gemini-b",
        "processing_openai_models": "gpt-a,gpt-b",
        "processing_claude_models": "claude-a,claude-b",
        "processing_deepseek_models": "ds-a",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _inv(**kwargs: object) -> Inventory:
    base = dict(
        id="inv-1",
        name="n",
        status=InventoryStatus.DRAFT,
        created_at=_NOW,
        updated_at=_NOW,
        processing_mode=InventoryProcessingMode.PRODUCTION,
        primary_provider_name="gemini",
        primary_model_name="gemini-prod-3.1",
        primary_prompt_key="global_v22",
    )
    base.update(kwargs)
    return Inventory(**base)


def test_production_catalog_gemini_default_model() -> None:
    s = _settings()
    assert production_provider_catalog(s) == {"gemini": "gemini-prod-3.1"}


def test_production_catalog_multiple_providers() -> None:
    s = _settings(
        openai_api_key="ok",
        anthropic_api_key="ak",
        llm_provider="openai",
    )
    cat = production_provider_catalog(s)
    assert cat == {
        "gemini": "gemini-prod-3.1",
        "openai": "gpt-prod",
        "claude": "claude-prod",
    }


def test_production_catalog_excludes_missing_credentials() -> None:
    s = _settings(openai_api_key="", anthropic_api_key="ak")
    cat = production_provider_catalog(s)
    assert "openai" not in cat
    assert "claude" in cat


def test_production_catalog_excludes_deepseek() -> None:
    s = _settings(deepseek_api_key="dk")
    assert "deepseek" not in production_provider_catalog(s)


def test_production_catalog_excludes_provider_without_explicit_model_env() -> None:
    s = _settings(gemini_model_name=None)
    assert "gemini" not in production_provider_catalog(s)


def test_effective_default_provider_falls_back_when_llm_provider_not_production_ready() -> None:
    s = _settings(llm_provider="openai", openai_api_key="")
    catalog = production_provider_catalog(s)
    effective, model = effective_production_default_provider_key(s, catalog)
    assert effective == "gemini"
    assert model == "gemini-prod-3.1"


def test_production_options_default_provider_when_openai_not_configured() -> None:
    s = _settings(llm_provider="openai", openai_api_key="")
    payload = build_processing_provider_options_payload(s, mode="production")
    assert payload["default_provider_key"] == "gemini"
    assert payload["default_model_key"] == "gemini-prod-3.1"
    assert all(p["key"] != "openai" for p in payload["providers"])
    gemini = next(p for p in payload["providers"] if p["key"] == "gemini")
    assert gemini["is_default_provider"] is True


def test_production_options_single_model_per_provider() -> None:
    s = _settings(openai_api_key="ok", anthropic_api_key="ak")
    payload = build_processing_provider_options_payload(s, mode="production")
    assert payload["mode"] == "production"
    assert payload["default_provider_key"] == "gemini"
    gemini = next(p for p in payload["providers"] if p["key"] == "gemini")
    openai_p = next(p for p in payload["providers"] if p["key"] == "openai")
    assert [m["id"] for m in gemini["models"]] == ["gemini-prod-3.1"]
    assert [m["id"] for m in openai_p["models"]] == ["gpt-prod"]


def test_test_mode_exposes_all_catalog_models() -> None:
    s = _settings()
    payload = build_processing_provider_options_payload(s, mode="test")
    gemini = next(p for p in payload["providers"] if p["key"] == "gemini")
    assert [m["id"] for m in gemini["models"]] == ["gemini-a", "gemini-b"]


def test_test_mode_excludes_deepseek() -> None:
    s = _settings(deepseek_api_key="dk")
    payload = build_processing_provider_options_payload(s, mode="test")
    assert all(p["key"] != "deepseek" for p in payload["providers"])


def test_resolve_production_explicit_deepseek_raises_deprecated() -> None:
    s = _settings(deepseek_api_key="dk", openai_api_key="ok")
    with pytest.raises(DeprecatedProcessingProviderError):
        resolve_production_processing_keys(
            _inv(),
            requested_provider_name="deepseek",
            requested_model_name=None,
            settings=s,
        )


def test_production_options_default_provider_openai() -> None:
    s = _settings(llm_provider="openai", openai_api_key="ok")
    payload = build_processing_provider_options_payload(s, mode="production")
    assert payload["default_provider_key"] == "openai"
    assert payload["default_model_key"] == "gpt-prod"


def test_resolve_production_honors_explicit_provider() -> None:
    s = _settings(openai_api_key="ok")
    p, m, pk = resolve_production_processing_keys(
        _inv(),
        requested_provider_name="openai",
        requested_model_name=None,
        settings=s,
    )
    assert (p, m, pk) == ("openai", "gpt-prod", "global_v22")


def test_resolve_production_rejects_non_default_model() -> None:
    s = _settings(openai_api_key="ok")
    with pytest.raises(InvalidProcessingModelError):
        resolve_production_processing_keys(
            _inv(),
            requested_provider_name="openai",
            requested_model_name="gpt-a",
            settings=s,
        )


def test_resolve_production_default_provider_from_env_when_no_request() -> None:
    s = _settings(llm_provider="openai", openai_api_key="ok")
    p, m, _ = resolve_production_processing_keys(
        _inv(primary_provider_name=None, primary_model_name=None),
        requested_provider_name=None,
        requested_model_name=None,
        settings=s,
    )
    assert (p, m) == ("openai", "gpt-prod")


def test_resolve_production_prefers_inventory_provider_over_llm_provider() -> None:
    s = _settings(llm_provider="openai", openai_api_key="ok")
    p, m, _ = resolve_production_processing_keys(
        _inv(primary_provider_name="gemini", primary_model_name="ignored-snapshot-model"),
        requested_provider_name=None,
        requested_model_name=None,
        settings=s,
    )
    assert (p, m) == ("gemini", "gemini-prod-3.1")


def test_resolve_production_ignores_snapshot_model_uses_current_catalog_default() -> None:
    s = _settings(openai_api_key="ok", openai_model="gpt-current")
    p, m, _ = resolve_production_processing_keys(
        _inv(primary_provider_name="openai", primary_model_name="gpt-stale-snapshot"),
        requested_provider_name=None,
        requested_model_name=None,
        settings=s,
    )
    assert (p, m) == ("openai", "gpt-current")


def test_resolve_production_unknown_provider_raises() -> None:
    with pytest.raises(UnknownProcessingProviderError):
        resolve_production_processing_keys(
            _inv(),
            requested_provider_name="not-a-provider",
            requested_model_name=None,
            settings=_settings(),
        )


def test_resolve_production_unconfigured_provider_raises() -> None:
    with pytest.raises(ProcessingProviderNotConfiguredError):
        resolve_production_processing_keys(
            _inv(),
            requested_provider_name="openai",
            requested_model_name=None,
            settings=_settings(openai_api_key=""),
        )


def test_resolve_production_no_providers_raises() -> None:
    s = _settings(gemini_api_key="", openai_api_key="", anthropic_api_key="")
    with pytest.raises(ProcessingProviderNotConfiguredError):
        resolve_production_processing_keys(
            _inv(),
            requested_provider_name=None,
            requested_model_name=None,
            settings=s,
        )


@patch(
    "src.application.services.process_aisle_execution_resolution.resolve_production_processing_keys"
)
def test_execution_resolution_production_delegates(mock_resolve) -> None:
    from src.application.services.process_aisle_execution_resolution import (
        resolve_process_aisle_execution_keys,
    )

    mock_resolve.return_value = ("claude", "claude-prod", "global_v22")
    out = resolve_process_aisle_execution_keys(
        _inv(),
        requested_provider_name="claude",
        requested_model_name="claude-prod",
        requested_prompt_key="global_v21",
        settings=object(),
    )
    assert out == ("claude", "claude-prod", "global_v22")
    mock_resolve.assert_called_once()
