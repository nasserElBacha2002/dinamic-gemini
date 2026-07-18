"""UpdateInventoryName use case — rename inventory display name."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.errors import InventoryNotFoundError
from src.application.ports.clock import Clock
from src.application.ports.repositories import InventoryRepository
from src.application.services.optional_unset import UNSET
from src.domain.inventory.entities import Inventory

_MAX_INVENTORY_NAME_LEN = 255


@dataclass
class UpdateInventoryNameCommand:
    inventory_id: str
    name: str
    #: UNSET = leave unchanged; None = clear override; mode = set.
    identification_mode: object = UNSET


class UpdateInventoryNameUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        clock: Clock,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._clock = clock

    def execute(self, command: UpdateInventoryNameCommand) -> Inventory:
        from src.domain.aisle_identification.modes import (
            AisleIdentificationMode,
            parse_identification_mode,
        )

        name = (command.name or "").strip()
        if not name:
            raise ValueError("Inventory name must not be empty")
        if len(name) > _MAX_INVENTORY_NAME_LEN:
            raise ValueError(f"Inventory name must be at most {_MAX_INVENTORY_NAME_LEN} characters")

        inventory = self._inventory_repo.get_by_id(command.inventory_id)
        if inventory is None:
            raise InventoryNotFoundError(f"Inventory not found: {command.inventory_id}")

        changed = False
        if inventory.name != name:
            inventory.name = name
            changed = True

        if command.identification_mode is not UNSET:
            mode = command.identification_mode
            if mode is not None and not isinstance(mode, AisleIdentificationMode):
                mode = parse_identification_mode(str(mode))
            if inventory.identification_mode != mode:
                inventory.identification_mode = mode  # type: ignore[assignment]
                changed = True

        if not changed:
            return inventory

        inventory.updated_at = self._clock.now()
        self._inventory_repo.save(inventory)
        return inventory
