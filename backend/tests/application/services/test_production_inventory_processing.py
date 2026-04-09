"""Effective processing keys for production inventories (snapshot + operational fallback)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from src.application.services.operational_execution_config_resolver import OperationalPrimaryExecutionConfig
from src.application.services.production_inventory_processing import effective_production_processing_keys
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus

_NOW = datetime(2026, 1, 2, tzinfo=timezone.utc)


def _inv(
    *,
    primary_provider_name: str | None = "db-provider",
    primary_model_name: str | None = "db-model",
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


@patch("src.application.services.production_inventory_processing.OperationalExecutionConfigResolver")
def test_full_snapshot_no_fallback_warning(mock_cls, caplog: pytest.LogCaptureFixture) -> None:
    mock_cls.return_value.resolve.return_value = OperationalPrimaryExecutionConfig(
        provider_name="resolver-p",
        model_name="resolver-m",
        prompt_key="resolver-pk",
        prompt_version=None,
    )
    caplog.set_level(logging.WARNING)
    p, m, pk = effective_production_processing_keys(_inv(), object())
    assert (p, m, pk) == ("db-provider", "db-model", "db-prompt")
    assert "production_inventory_snapshot_incomplete" not in caplog.text


@patch("src.application.services.production_inventory_processing.OperationalExecutionConfigResolver")
def test_partial_snapshot_logs_and_fills_from_resolver(mock_cls, caplog: pytest.LogCaptureFixture) -> None:
    mock_cls.return_value.resolve.return_value = OperationalPrimaryExecutionConfig(
        provider_name="fill-p",
        model_name="fill-m",
        prompt_key="fill-pk",
        prompt_version="v9",
    )
    caplog.set_level(logging.WARNING)
    inv = _inv(
        primary_provider_name=None,
        primary_model_name="db-model",
        primary_prompt_key="db-prompt",
    )
    p, m, pk = effective_production_processing_keys(inv, object())
    assert p == "fill-p"
    assert m == "db-model"
    assert pk == "db-prompt"
    assert "production_inventory_snapshot_incomplete_using_operational_fallback" in caplog.text
    assert "inv-prod" in caplog.text
    assert "primary_provider_name" in caplog.text
