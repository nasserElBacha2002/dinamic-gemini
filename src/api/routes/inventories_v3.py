"""
v3.0 Inventories API — HTTP layer only.

Delegates to application use cases. No business logic here.
Dependencies (repo, clock, use cases) provided by api.dependencies.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import (
    get_create_aisle_use_case,
    get_create_inventory_use_case,
    get_get_aisle_processing_status_use_case,
    get_get_inventory_use_case,
    get_list_aisles_with_status_use_case,
    get_list_inventories_use_case,
    get_start_aisle_processing_use_case,
)
from src.api.schemas.aisle_schemas import CreateAisleRequest, AisleResponse, AisleJobSummary
from src.api.schemas.processing_schemas import AisleStatusResponse, JobSummary, ProcessAisleResponse
from src.api.schemas.inventory_schemas import CreateInventoryRequest, InventoryResponse
from src.application.errors import ActiveJobExistsError, AisleNotFoundError, DuplicateAisleCodeError, InventoryNotFoundError
from src.application.use_cases.create_aisle import CreateAisleCommand, CreateAisleUseCase
from src.application.use_cases.create_inventory import CreateInventoryCommand, CreateInventoryUseCase
from src.application.use_cases.get_aisle_processing_status import (
    AisleProcessingStatusResult,
    GetAisleProcessingStatusUseCase,
)
from src.application.use_cases.get_inventory import GetInventoryUseCase
from src.application.use_cases.list_aisles_with_status import ListAislesWithStatusUseCase
from src.application.use_cases.list_inventories import ListInventoriesUseCase
from src.application.use_cases.start_aisle_processing import StartAisleProcessingCommand, StartAisleProcessingUseCase
from src.domain.aisle.entities import Aisle
from src.domain.inventory.entities import Inventory
from src.domain.jobs.entities import Job

router = APIRouter(prefix="/api/v3/inventories", tags=["inventories-v3"])


def _inventory_to_response(inv: Inventory) -> InventoryResponse:
    return InventoryResponse(
        id=inv.id,
        name=inv.name,
        status=inv.status.value,
        created_at=inv.created_at,
    )


def _aisle_to_response(a: Aisle, latest_job: Optional[Job] = None) -> AisleResponse:
    latest = None
    if latest_job is not None:
        latest = AisleJobSummary(
            id=latest_job.id,
            status=latest_job.status.value,
            updated_at=latest_job.updated_at,
        )
    return AisleResponse(
        id=a.id,
        inventory_id=a.inventory_id,
        code=a.code,
        status=a.status.value,
        created_at=a.created_at,
        updated_at=a.updated_at,
        error_code=a.error_code,
        error_message=a.error_message,
        latest_job=latest,
    )


def _status_response_from_result(result: AisleProcessingStatusResult) -> AisleStatusResponse:
    """Compose status DTO from use-case result; keeps route thin."""
    job_summary = None
    if result.latest_job is not None:
        j = result.latest_job
        job_summary = JobSummary(
            id=j.id,
            status=j.status.value,
            created_at=j.created_at,
            updated_at=j.updated_at,
            error_message=j.error_message,
        )
    return AisleStatusResponse(
        aisle=_aisle_to_response(result.aisle, result.latest_job),
        latest_job=job_summary,
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
    use_case: ListAislesWithStatusUseCase = Depends(get_list_aisles_with_status_use_case),
) -> List[AisleResponse]:
    """List aisles for an inventory (v3.0). Returns 404 if inventory not found. Includes latest job per aisle."""
    try:
        items = use_case.execute(inventory_id)
        return [_aisle_to_response(item.aisle, item.latest_job) for item in items]
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail="Inventory not found")


@router.post("/{inventory_id}/aisles/{aisle_id}/process", response_model=ProcessAisleResponse, status_code=202)
def start_aisle_processing(
    inventory_id: str,
    aisle_id: str,
    use_case: StartAisleProcessingUseCase = Depends(get_start_aisle_processing_use_case),
) -> ProcessAisleResponse:
    try:
        job_id = use_case.execute(StartAisleProcessingCommand(inventory_id=inventory_id, aisle_id=aisle_id))
        return ProcessAisleResponse(job_id=job_id)
    except AisleNotFoundError:
        raise HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")
    except ActiveJobExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/{inventory_id}/aisles/{aisle_id}/status", response_model=AisleStatusResponse)
def get_aisle_status(
    inventory_id: str,
    aisle_id: str,
    use_case: GetAisleProcessingStatusUseCase = Depends(get_get_aisle_processing_status_use_case),
) -> AisleStatusResponse:
    try:
        result = use_case.execute(inventory_id, aisle_id)
        return _status_response_from_result(result)
    except AisleNotFoundError:
        raise HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")
