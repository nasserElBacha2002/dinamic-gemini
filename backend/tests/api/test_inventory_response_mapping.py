"""Inventory API mapping — primary_execution_config only when snapshot is complete."""

from __future__ import annotations

from datetime import datetime, timezone

from src.api.routes.v3.shared import inventory_to_response
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus

_NOW = datetime(2026, 3, 1, tzinfo=timezone.utc)


def _base_inv(
    *,
    processing_mode: InventoryProcessingMode = InventoryProcessingMode.PRODUCTION,
    primary_provider_name: str | None = "p",
    primary_model_name: str | None = "m",
    primary_prompt_key: str | None = "pk",
    primary_prompt_version: str | None = "v1",
) -> Inventory:
    return Inventory(
        id="i1",
        name="N",
        status=InventoryStatus.DRAFT,
        created_at=_NOW,
        updated_at=_NOW,
        processing_mode=processing_mode,
        primary_provider_name=primary_provider_name,
        primary_model_name=primary_model_name,
        primary_prompt_key=primary_prompt_key,
        primary_prompt_version=primary_prompt_version,
    )


def test_production_with_full_snapshot_exposes_primary_execution_config() -> None:
    body = inventory_to_response(_base_inv()).model_dump()
    assert body["primary_execution_config"] is not None
    assert body["primary_execution_config"]["provider_name"] == "p"
    assert body["primary_execution_config"]["model_name"] == "m"
    assert body["primary_execution_config"]["prompt_key"] == "pk"


def test_production_with_incomplete_snapshot_omits_primary_block() -> None:
    body = inventory_to_response(_base_inv(primary_model_name="")).model_dump()
    assert body["primary_execution_config"] is None


def test_test_inventory_never_exposes_primary_execution_config() -> None:
    body = inventory_to_response(
        _base_inv(processing_mode=InventoryProcessingMode.TEST, primary_model_name="")
    ).model_dump()
    assert body["primary_execution_config"] is None
