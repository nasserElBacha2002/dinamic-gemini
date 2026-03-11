"""
GetInventory use case — v3.0.

Returns a single inventory by id. Raises InventoryNotFoundError if not found.
"""

from __future__ import annotations

from src.application.errors import InventoryNotFoundError
from src.application.ports.repositories import InventoryRepository
from src.domain.inventory.entities import Inventory


class GetInventoryUseCase:
    def __init__(self, inventory_repo: InventoryRepository) -> None:
        self._inventory_repo = inventory_repo

    def execute(self, inventory_id: str) -> Inventory:
        inv = self._inventory_repo.get_by_id(inventory_id)
        if inv is None:
            raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")
        return inv
