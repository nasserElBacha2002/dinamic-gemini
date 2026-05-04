"""Tests for :mod:`src.application.services.inventory_primary_execution_config`."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.services.inventory_primary_execution_config import (
    primary_execution_config_for_inventory,
)
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus

_NOW = datetime(2026, 3, 1, tzinfo=timezone.utc)


def _inv(
    *,
    mode: InventoryProcessingMode = InventoryProcessingMode.PRODUCTION,
    pn: str | None = "p",
    pm: str | None = "m",
    pk: str | None = "k",
    pv: str | None = "v",
) -> Inventory:
    return Inventory(
        id="i",
        name="n",
        status=InventoryStatus.DRAFT,
        created_at=_NOW,
        updated_at=_NOW,
        processing_mode=mode,
        primary_provider_name=pn,
        primary_model_name=pm,
        primary_prompt_key=pk,
        primary_prompt_version=pv,
    )


def test_production_complete_returns_fields() -> None:
    f = primary_execution_config_for_inventory(_inv())
    assert f is not None
    assert f.provider_name == "p"
    assert f.model_name == "m"
    assert f.prompt_key == "k"
    assert f.prompt_version == "v"


def test_non_production_returns_none() -> None:
    assert primary_execution_config_for_inventory(_inv(mode=InventoryProcessingMode.TEST)) is None


def test_whitespace_only_placeholders_returns_none() -> None:
    assert primary_execution_config_for_inventory(_inv(pm="   ")) is None
