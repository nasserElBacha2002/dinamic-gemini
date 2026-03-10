"""
GetInventory use case — v3.0.

Returns a single inventory by id. Used for inventory detail and for validating parent existence.
"""

from __future__ import annotations

from typing import Optional

from src.application.ports.repositories import InventoryRepository
from src.domain.inventory.entities import Inventory


class GetInventoryUseCase:
    def __init__(self, inventory_repo: InventoryRepository) -> None:
        self._inventory_repo = inventory_repo

    def execute(self, inventory_id: str) -> Optional[Inventory]:
        return self._inventory_repo.get_by_id(inventory_id)
