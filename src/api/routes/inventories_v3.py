"""
v3.0 Inventories API — HTTP layer only.

Delegates to application use cases. No business logic here.
Dependencies (repo, clock, use cases) provided by api.dependencies.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from typing import List

from src.api.dependencies import (
    get_create_inventory_use_case,
    get_list_inventories_use_case,
)
from src.api.schemas.inventory_schemas import CreateInventoryRequest, InventoryResponse
from src.application.use_cases.create_inventory import CreateInventoryCommand, CreateInventoryUseCase
from src.application.use_cases.list_inventories import ListInventoriesUseCase

router = APIRouter(prefix="/api/v3/inventories", tags=["inventories-v3"])


@router.post("", response_model=InventoryResponse, status_code=201)
def create_inventory(
    payload: CreateInventoryRequest,
    use_case: CreateInventoryUseCase = Depends(get_create_inventory_use_case),
) -> InventoryResponse:
    """Create a new inventory (v3.0)."""
    inventory = use_case.execute(CreateInventoryCommand(name=payload.name))
    return InventoryResponse(id=inventory.id, name=inventory.name, status=inventory.status.value)


@router.get("", response_model=List[InventoryResponse])
def list_inventories(
    use_case: ListInventoriesUseCase = Depends(get_list_inventories_use_case),
) -> List[InventoryResponse]:
    """List all inventories (v3.0)."""
    inventories = use_case.execute()
    return [
        InventoryResponse(id=inv.id, name=inv.name, status=inv.status.value)
        for inv in inventories
    ]
