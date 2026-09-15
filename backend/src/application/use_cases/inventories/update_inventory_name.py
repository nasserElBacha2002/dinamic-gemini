"""Update inventory (name and/or identification mode override) — tenant-scoped."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.dto.access_principal import AccessPrincipal
from src.application.ports.clock import Clock
from src.application.ports.repositories import InventoryRepository
from src.application.services.inventory_access_policy import InventoryAccessPolicy
from src.application.services.legacy_processing_guard import (
    reject_legacy_mode_for_new_configuration,
)
from src.application.services.optional_unset import UNSET, OptionalModeUpdate, UnsetType
from src.domain.aisle_identification.modes import AisleIdentificationMode, parse_identification_mode
from src.domain.inventory.entities import Inventory

_MAX_INVENTORY_NAME_LEN = 255


@dataclass
class UpdateInventoryCommand:
    inventory_id: str
    principal: AccessPrincipal
    name: str | None = None
    identification_mode: OptionalModeUpdate = UNSET


# Backward-compatible alias for DI / existing imports.
UpdateInventoryNameCommand = UpdateInventoryCommand


class UpdateInventoryUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        clock: Clock,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._clock = clock
        self._policy = InventoryAccessPolicy(inventory_repo)

    def execute(self, command: UpdateInventoryCommand) -> Inventory:
        if command.name is None and isinstance(command.identification_mode, UnsetType):
            raise ValueError("At least one field must be provided")

        inventory = self._policy.require_inventory(command.inventory_id, command.principal)

        changed = False
        if command.name is not None:
            name = command.name.strip()
            if not name:
                raise ValueError("Inventory name must not be empty")
            if len(name) > _MAX_INVENTORY_NAME_LEN:
                raise ValueError(
                    f"Inventory name must be at most {_MAX_INVENTORY_NAME_LEN} characters"
                )
            if inventory.name != name:
                inventory.name = name
                changed = True

        if not isinstance(command.identification_mode, UnsetType):
            mode: AisleIdentificationMode | None
            if command.identification_mode is None:
                mode = None
            elif isinstance(command.identification_mode, AisleIdentificationMode):
                mode = command.identification_mode
            else:
                mode = parse_identification_mode(command.identification_mode)
            reject_legacy_mode_for_new_configuration(mode, context="inventory")
            if inventory.identification_mode != mode:
                inventory.identification_mode = mode
                changed = True

        if not changed:
            return inventory

        inventory.updated_at = self._clock.now()
        self._inventory_repo.save(inventory)
        return inventory


# Backward-compatible alias.
UpdateInventoryNameUseCase = UpdateInventoryUseCase
