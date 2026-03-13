"""v3 inventory CRUD and metrics."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import (
    get_create_inventory_use_case,
    get_list_inventories_use_case,
    get_get_inventory_use_case,
    get_get_inventory_metrics_use_case,
)
from src.api.schemas.inventory_schemas import (
    CreateInventoryRequest,
    InventoryResponse,
    InventoryMetricsResponse,
)
from src.application.errors import InventoryNotFoundError
from src.application.use_cases.create_inventory import CreateInventoryCommand, CreateInventoryUseCase
from src.application.use_cases.get_inventory import GetInventoryUseCase
from src.application.use_cases.get_inventory_metrics import GetInventoryMetricsUseCase
from src.application.use_cases.list_inventories import ListInventoriesUseCase

from .shared import inventory_to_response

router = APIRouter()


@router.post("/", response_model=InventoryResponse, status_code=201)
def create_inventory(
    payload: CreateInventoryRequest,
    use_case: CreateInventoryUseCase = Depends(get_create_inventory_use_case),
) -> InventoryResponse:
    """Create a new inventory (v3.0)."""
    inventory = use_case.execute(CreateInventoryCommand(name=payload.name))
    return inventory_to_response(inventory)


@router.get("/", response_model=List[InventoryResponse])
def list_inventories(
    use_case: ListInventoriesUseCase = Depends(get_list_inventories_use_case),
) -> List[InventoryResponse]:
    """List all inventories (v3.0)."""
    inventories = use_case.execute()
    return [inventory_to_response(inv) for inv in inventories]


@router.get("/{inventory_id}", response_model=InventoryResponse)
def get_inventory(
    inventory_id: str,
    use_case: GetInventoryUseCase = Depends(get_get_inventory_use_case),
) -> InventoryResponse:
    """Get a single inventory by id (v3.0). Returns 404 if not found."""
    try:
        inventory = use_case.execute(inventory_id)
        return inventory_to_response(inventory)
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail="Inventory not found")


@router.get("/{inventory_id}/metrics", response_model=InventoryMetricsResponse)
def get_inventory_metrics(
    inventory_id: str,
    use_case: GetInventoryMetricsUseCase = Depends(get_get_inventory_metrics_use_case),
) -> InventoryMetricsResponse:
    """Get canonical inventory metrics. Returns 404 if inventory not found."""
    try:
        metrics = use_case.execute(inventory_id)
        return InventoryMetricsResponse(**metrics)
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail="Inventory not found")
