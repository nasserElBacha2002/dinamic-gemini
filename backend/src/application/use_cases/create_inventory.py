"""
CreateInventory use case — v3.0 (Backlog HU-2.1).

Creates an inventory with the given name and persists it via InventoryRepository.
Depends only on application ports and domain entities.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from src.application.ports.clock import Clock
from src.application.ports.repositories import InventoryRepository
from src.domain.inventory.entities import Inventory, InventoryStatus


@dataclass
class CreateInventoryCommand:
    name: str


class CreateInventoryUseCase:
    def __init__(self, inventory_repo: InventoryRepository, clock: Clock) -> None:
        self._inventory_repo = inventory_repo
        self._clock = clock

    def execute(self, command: CreateInventoryCommand) -> Inventory:
        now = self._clock.now()
        inventory = Inventory(
            id=str(uuid4()),
            name=command.name,
            status=InventoryStatus.DRAFT,
            created_at=now,
            updated_at=now,
        )
        self._inventory_repo.save(inventory)
        return inventory
