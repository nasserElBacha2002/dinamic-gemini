"""Resolve provider/model/prompt for aisle process — production vs test."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from src.application.services.process_aisle_execution_resolution import (
    resolve_process_aisle_execution_keys,
)
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _inv(
    *,
    mode: InventoryProcessingMode,
    primary_provider: str | None = "snap-p",
    primary_model: str | None = "snap-m",
    primary_prompt: str | None = "snap-pk",
) -> Inventory:
    return Inventory(
        id="inv-1",
        name="n",
        status=InventoryStatus.DRAFT,
        created_at=_NOW,
        updated_at=_NOW,
        processing_mode=mode,
        primary_provider_name=primary_provider,
        primary_model_name=primary_model,
        primary_prompt_key=primary_prompt,
    )


@patch(
    "src.application.services.process_aisle_execution_resolution.resolve_production_processing_keys"
)
def test_production_delegates_to_production_resolver(mock_resolve) -> None:
    mock_resolve.return_value = ("gemini", "m1", "global_v22")
    settings = object()
    out = resolve_process_aisle_execution_keys(
        _inv(mode=InventoryProcessingMode.PRODUCTION),
        requested_provider_name="openai",
        requested_model_name="gpt",
        requested_prompt_key=None,
        settings=settings,
    )
    assert out == ("gemini", "m1", "global_v22")
    mock_resolve.assert_called_once_with(
        _inv(mode=InventoryProcessingMode.PRODUCTION),
        requested_provider_name="openai",
        requested_model_name="gpt",
        settings=settings,
    )


@patch(
    "src.application.services.process_aisle_execution_resolution.resolve_start_processing_request"
)
def test_test_mode_delegates_to_resolve_start(mock_resolve) -> None:
    mock_resolve.return_value = ("openai", "gpt", "custom")
    settings = object()
    out = resolve_process_aisle_execution_keys(
        _inv(mode=InventoryProcessingMode.TEST),
        requested_provider_name="openai",
        requested_model_name="gpt",
        requested_prompt_key="custom",
        settings=settings,
    )
    assert out == ("openai", "gpt", "custom")
    mock_resolve.assert_called_once()


@patch(
    "src.application.services.process_aisle_execution_resolution.resolve_production_processing_keys"
)
def test_production_logs_when_prompt_override_sent(
    mock_resolve, caplog: pytest.LogCaptureFixture
) -> None:
    mock_resolve.return_value = ("p", "m", "global_v22")
    caplog.set_level(logging.WARNING)
    resolve_process_aisle_execution_keys(
        _inv(mode=InventoryProcessingMode.PRODUCTION),
        requested_provider_name=None,
        requested_model_name=None,
        requested_prompt_key="global_v21",
        settings=object(),
    )
    assert "production_process_ignoring_prompt_override" in caplog.text
    assert "inv-1" in caplog.text
