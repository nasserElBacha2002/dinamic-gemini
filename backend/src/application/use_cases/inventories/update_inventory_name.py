"""UpdateInventoryName use case — rename inventory display name."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.errors import InventoryNotFoundError
from src.application.ports.clock import Clock
from src.application.ports.repositories import InventoryRepository
from src.domain.inventory.entities import Inventory

_MAX_INVENTORY_NAME_LEN = 255


@dataclass
class UpdateInventoryNameCommand:
    inventory_id: str
    name: str


class UpdateInventoryNameUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        clock: Clock,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._clock = clock

    def execute(self, command: UpdateInventoryNameCommand) -> Inventory:
        name = (command.name or "").strip()
        if not name:
            raise ValueError("Inventory name must not be empty")
        if len(name) > _MAX_INVENTORY_NAME_LEN:
            raise ValueError(f"Inventory name must be at most {_MAX_INVENTORY_NAME_LEN} characters")

        inventory = self._inventory_repo.get_by_id(command.inventory_id)
        if inventory is None:
            raise InventoryNotFoundError(f"Inventory not found: {command.inventory_id}")

        if inventory.name == name:
            return inventory

        inventory.name = name
        inventory.updated_at = self._clock.now()
        self._inventory_repo.save(inventory)
        return inventory
