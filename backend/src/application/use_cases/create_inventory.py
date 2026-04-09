"""
CreateInventory use case — v3.0 (Backlog HU-2.1).

Creates an inventory with the given name and persists it via InventoryRepository.
Depends only on application ports and domain entities.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from uuid import uuid4

from src.application.ports.clock import Clock
from src.application.ports.repositories import InventoryRepository
from src.application.services.operational_execution_config_resolver import (
    OperationalExecutionConfigResolver,
)
from src.domain.inventory.entities import (
    Inventory,
    InventoryProcessingMode,
    InventoryStatus,
)


@dataclass
class CreateInventoryCommand:
    name: str
    processing_mode: InventoryProcessingMode = InventoryProcessingMode.PRODUCTION


class CreateInventoryUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        clock: Clock,
        operational_resolver: OperationalExecutionConfigResolver,
        settings_loader: Callable[[], Any],
    ) -> None:
        self._inventory_repo = inventory_repo
        self._clock = clock
        self._operational_resolver = operational_resolver
        self._settings_loader = settings_loader

    def execute(self, command: CreateInventoryCommand) -> Inventory:
        now = self._clock.now()
        mode = command.processing_mode
        primary_provider_name = None
        primary_model_name = None
        primary_prompt_key = None
        primary_prompt_version = None
        if mode == InventoryProcessingMode.PRODUCTION:
            settings = self._settings_loader()
            snap = self._operational_resolver.resolve(settings)
            primary_provider_name = snap.provider_name
            primary_model_name = snap.model_name
            primary_prompt_key = snap.prompt_key
            primary_prompt_version = snap.prompt_version
        inventory = Inventory(
            id=str(uuid4()),
            name=command.name,
            status=InventoryStatus.DRAFT,
            created_at=now,
            updated_at=now,
            processing_mode=mode,
            primary_provider_name=primary_provider_name,
            primary_model_name=primary_model_name,
            primary_prompt_key=primary_prompt_key,
            primary_prompt_version=primary_prompt_version,
        )
        self._inventory_repo.save(inventory)
        return inventory
