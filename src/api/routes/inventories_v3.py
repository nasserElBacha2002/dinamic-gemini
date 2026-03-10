"""
v3.0 Inventories API — HTTP layer only.

Delegates to application use cases. No business logic here.
Dependencies (repo, clock, use cases) provided by api.dependencies.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import (
    get_create_aisle_use_case,
    get_create_inventory_use_case,
    get_get_inventory_use_case,
    get_list_aisles_by_inventory_use_case,
    get_list_inventories_use_case,
)
from src.api.schemas.aisle_schemas import CreateAisleRequest, AisleResponse
from src.api.schemas.inventory_schemas import CreateInventoryRequest, InventoryResponse
from src.application.use_cases.create_aisle import CreateAisleCommand, CreateAisleUseCase, DuplicateAisleCodeError, InventoryNotFoundError
from src.application.use_cases.create_inventory import CreateInventoryCommand, CreateInventoryUseCase
from src.application.use_cases.get_inventory import GetInventoryUseCase
from src.application.use_cases.list_aisles_by_inventory import ListAislesByInventoryUseCase
from src.application.use_cases.list_inventories import ListInventoriesUseCase
from src.domain.aisle.entities import Aisle
from src.domain.inventory.entities import Inventory

router = APIRouter(prefix="/api/v3/inventories", tags=["inventories-v3"])


def _inventory_to_response(inv: Inventory) -> InventoryResponse:
    return InventoryResponse(
        id=inv.id,
        name=inv.name,
        status=inv.status.value,
        created_at=inv.created_at,
    )


def _aisle_to_response(a: Aisle) -> AisleResponse:
    return AisleResponse(
        id=a.id,
        inventory_id=a.inventory_id,
        code=a.code,
        status=a.status.value,
        created_at=a.created_at,
        updated_at=a.updated_at,
        error_code=a.error_code,
        error_message=a.error_message,
    )


@router.post("", response_model=InventoryResponse, status_code=201)
def create_inventory(
    payload: CreateInventoryRequest,
    use_case: CreateInventoryUseCase = Depends(get_create_inventory_use_case),
) -> InventoryResponse:
    """Create a new inventory (v3.0)."""
    inventory = use_case.execute(CreateInventoryCommand(name=payload.name))
    return _inventory_to_response(inventory)


@router.get("", response_model=List[InventoryResponse])
def list_inventories(
    use_case: ListInventoriesUseCase = Depends(get_list_inventories_use_case),
) -> List[InventoryResponse]:
    """List all inventories (v3.0)."""
    inventories = use_case.execute()
    return [_inventory_to_response(inv) for inv in inventories]


@router.get("/{inventory_id}", response_model=InventoryResponse)
def get_inventory(
    inventory_id: str,
    use_case: GetInventoryUseCase = Depends(get_get_inventory_use_case),
) -> InventoryResponse:
    """Get a single inventory by id (v3.0). Returns 404 if not found."""
    inventory = use_case.execute(inventory_id)
    if inventory is None:
        raise HTTPException(status_code=404, detail="Inventory not found")
    return _inventory_to_response(inventory)


@router.post("/{inventory_id}/aisles", response_model=AisleResponse, status_code=201)
def create_aisle(
    inventory_id: str,
    payload: CreateAisleRequest,
    use_case: CreateAisleUseCase = Depends(get_create_aisle_use_case),
) -> AisleResponse:
    """Create an aisle in an inventory (v3.0). Returns 404 if inventory not found, 409 if code duplicate."""
    try:
        aisle = use_case.execute(CreateAisleCommand(inventory_id=inventory_id, code=payload.code))
        return _aisle_to_response(aisle)
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail="Inventory not found")
    except DuplicateAisleCodeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/{inventory_id}/aisles", response_model=List[AisleResponse])
def list_aisles(
    inventory_id: str,
    use_case: ListAislesByInventoryUseCase = Depends(get_list_aisles_by_inventory_use_case),
) -> List[AisleResponse]:
    """List aisles for an inventory (v3.0). Returns 404 if inventory not found."""
    try:
        aisles = use_case.execute(inventory_id)
        return [_aisle_to_response(a) for a in aisles]
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail="Inventory not found")
