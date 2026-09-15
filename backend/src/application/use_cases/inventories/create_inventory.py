"""
CreateInventory use case — v3.0 (Backlog HU-2.1).

Creates an inventory with the given name and persists it via InventoryRepository.
Depends only on application ports and domain entities.

Authorization and tenant checks run **before** expensive processing-config resolution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from uuid import uuid4

from src.application.dto.access_principal import AccessPrincipal
from src.application.errors import ClientNotFoundError
from src.application.ports.clock import Clock
from src.application.ports.repositories import ClientRepository, InventoryRepository
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
    client_id: str
    principal: AccessPrincipal
    processing_mode: InventoryProcessingMode = InventoryProcessingMode.PRODUCTION


class CreateInventoryUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        client_repo: ClientRepository,
        clock: Clock,
        operational_resolver: OperationalExecutionConfigResolver,
        settings_loader: Callable[[], Any],
    ) -> None:
        self._inventory_repo = inventory_repo
        self._client_repo = client_repo
        self._clock = clock
        self._operational_resolver = operational_resolver
        self._settings_loader = settings_loader

    def execute(self, command: CreateInventoryCommand) -> Inventory:
        requested_client_id = (command.client_id or "").strip()
        if not requested_client_id:
            raise ValueError("client_id must not be empty")
        # Never trust body tenant for company-scoped principals.
        if command.principal.is_platform:
            client_id = requested_client_id
        else:
            principal_client = (command.principal.client_id or "").strip() or None
            if principal_client is None:
                raise ClientNotFoundError(f"Client not found: {requested_client_id}")
            if requested_client_id != principal_client:
                raise ClientNotFoundError(f"Client not found: {requested_client_id}")
            client_id = principal_client
        if self._client_repo.get_by_id(client_id) is None:
            raise ClientNotFoundError(f"Client not found: {client_id}")

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
            client_id=client_id,
        )
        self._inventory_repo.save(inventory)
        return inventory
