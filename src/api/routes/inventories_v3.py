"""
v3.0 Inventories API — HTTP layer only.

Delegates to application use cases. No business logic here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from typing import List, Optional

from src.api.schemas.inventory_schemas import CreateInventoryRequest, InventoryResponse
from src.application.ports.repositories import InventoryRepository
from src.application.use_cases.create_inventory import CreateInventoryCommand, CreateInventoryUseCase
from src.application.use_cases.list_inventories import ListInventoriesUseCase

router = APIRouter(prefix="/api/v3/inventories", tags=["inventories-v3"])

# Single in-memory repo instance so POST/GET share state within process (no DB in this slice).
_inventory_repo: Optional[InventoryRepository] = None


def _get_inventory_repo() -> InventoryRepository:
    global _inventory_repo
    if _inventory_repo is None:
        from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
        _inventory_repo = MemoryInventoryRepository()
    return _inventory_repo


def _get_clock():
    from src.infrastructure.adapters.clock import UtcClock
    return UtcClock()


def _get_create_inventory_use_case(
    repo: InventoryRepository = Depends(_get_inventory_repo),
    clock=Depends(_get_clock),
) -> CreateInventoryUseCase:
    return CreateInventoryUseCase(inventory_repo=repo, clock=clock)


def _get_list_inventories_use_case(
    repo: InventoryRepository = Depends(_get_inventory_repo),
) -> ListInventoriesUseCase:
    return ListInventoriesUseCase(inventory_repo=repo)


@router.post("", response_model=InventoryResponse, status_code=201)
def create_inventory(
    payload: CreateInventoryRequest,
    use_case: CreateInventoryUseCase = Depends(_get_create_inventory_use_case),
) -> InventoryResponse:
    """Create a new inventory (v3.0)."""
    inventory = use_case.execute(CreateInventoryCommand(name=payload.name))
    return InventoryResponse(id=inventory.id, name=inventory.name, status=inventory.status.value)


@router.get("", response_model=List[InventoryResponse])
def list_inventories(
    use_case: ListInventoriesUseCase = Depends(_get_list_inventories_use_case),
) -> List[InventoryResponse]:
    """List all inventories (v3.0)."""
    inventories = use_case.execute()
    return [
        InventoryResponse(id=inv.id, name=inv.name, status=inv.status.value)
        for inv in inventories
    ]
