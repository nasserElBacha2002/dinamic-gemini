"""
GetInventory use case — v3.0 (tenant-scoped Stage 2).

Returns a single inventory by id when the principal may access it.
Raises InventoryNotFoundError if missing, soft-deleted, or cross-tenant.
"""

from __future__ import annotations

from src.application.dto.access_principal import AccessPrincipal
from src.application.ports.repositories import InventoryRepository
from src.application.services.inventory_access_policy import InventoryAccessPolicy
from src.domain.inventory.entities import Inventory


class GetInventoryUseCase:
    def __init__(self, inventory_repo: InventoryRepository) -> None:
        self._policy = InventoryAccessPolicy(inventory_repo)

    def execute(self, inventory_id: str, principal: AccessPrincipal) -> Inventory:
        return self._policy.require_inventory(inventory_id, principal)
