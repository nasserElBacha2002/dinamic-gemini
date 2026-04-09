"""Tests for CreateInventoryUseCase."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.application.ports.repositories import InventoryRepository
from src.application.services.operational_execution_config_resolver import (
    OperationalPrimaryExecutionConfig,
)
from src.application.use_cases.create_inventory import CreateInventoryCommand, CreateInventoryUseCase
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class StubInventoryRepo(InventoryRepository):
    def __init__(self) -> None:
        self._store: dict[str, Inventory] = {}

    def save(self, inventory: Inventory) -> None:
        self._store[inventory.id] = inventory

    def get_by_id(self, inventory_id: str):
        return self._store.get(inventory_id)

    def list_all(self):
        return list(self._store.values())


class StubOperationalResolver:
    def resolve(self, settings: Any) -> OperationalPrimaryExecutionConfig:
        _ = settings
        return OperationalPrimaryExecutionConfig(
            provider_name="fake",
            model_name="fixture",
            prompt_key="global_v21",
            prompt_version=None,
        )


def _dummy_settings() -> object:
    return object()


def test_create_inventory_production_snapshots_operational_config() -> None:
    repo = StubInventoryRepo()
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    clock = FixedClock(now)
    use_case = CreateInventoryUseCase(
        inventory_repo=repo,
        clock=clock,
        operational_resolver=StubOperationalResolver(),
        settings_loader=_dummy_settings,
    )

    result = use_case.execute(CreateInventoryCommand(name="Warehouse A"))

    assert result.name == "Warehouse A"
    assert result.status == InventoryStatus.DRAFT
    assert result.processing_mode == InventoryProcessingMode.PRODUCTION
    assert result.primary_provider_name == "fake"
    assert result.primary_model_name == "fixture"
    assert result.primary_prompt_key == "global_v21"
    assert result.created_at == now
    assert result.updated_at == now
    assert repo.get_by_id(result.id) == result
    assert len(repo.list_all()) == 1


def test_create_inventory_test_leaves_primary_fields_null() -> None:
    repo = StubInventoryRepo()
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    clock = FixedClock(now)
    use_case = CreateInventoryUseCase(
        inventory_repo=repo,
        clock=clock,
        operational_resolver=StubOperationalResolver(),
        settings_loader=_dummy_settings,
    )

    result = use_case.execute(
        CreateInventoryCommand(name="Lab", processing_mode=InventoryProcessingMode.TEST)
    )

    assert result.processing_mode == InventoryProcessingMode.TEST
    assert result.primary_provider_name is None
    assert result.primary_model_name is None
    assert result.primary_prompt_key is None
    assert result.primary_prompt_version is None
