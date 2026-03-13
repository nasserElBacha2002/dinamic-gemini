"""v3 aisle CRUD, process, status, execution log."""

from __future__ import annotations

from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from src.config import load_settings
from src.api.dependencies import (
    get_create_aisle_use_case,
    get_list_aisles_with_status_use_case,
    get_start_aisle_processing_use_case,
    get_get_aisle_processing_status_use_case,
    get_cancel_aisle_job_use_case,
    get_aisle_repo,
    get_job_repo,
)
from src.api.schemas.aisle_schemas import AisleResponse, CreateAisleRequest
from src.api.schemas.processing_schemas import (
    AisleStatusResponse,
    ExecutionLogEvent,
    ExecutionLogResponse,
    ProcessAisleResponse,
)
from src.application.ports.repositories import AisleRepository, JobRepository
from src.application.errors import AisleNotFoundError, ActiveJobExistsError, DuplicateAisleCodeError, InventoryNotFoundError
from src.application.use_cases.create_aisle import CreateAisleCommand, CreateAisleUseCase
from src.application.use_cases.list_aisles_with_status import ListAislesWithStatusUseCase
from src.application.use_cases.start_aisle_processing import StartAisleProcessingCommand, StartAisleProcessingUseCase
from src.application.use_cases.get_aisle_processing_status import GetAisleProcessingStatusUseCase
from src.application.use_cases.cancel_aisle_job import CancelAisleJobCommand, CancelAisleJobUseCase
from src.infrastructure.pipeline.v3_job_executor import RUN_ID
from src.pipeline.execution_log import read_execution_log

from .shared import aisle_to_response, status_response_from_result

router = APIRouter()


@router.post("/{inventory_id}/aisles", response_model=AisleResponse, status_code=201)
def create_aisle(
    inventory_id: str,
    payload: CreateAisleRequest,
    use_case: CreateAisleUseCase = Depends(get_create_aisle_use_case),
) -> AisleResponse:
    """Create an aisle in an inventory (v3.0). Returns 404 if inventory not found, 409 if code duplicate."""
    try:
        aisle = use_case.execute(CreateAisleCommand(inventory_id=inventory_id, code=payload.code))
        return aisle_to_response(aisle)
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
        return [aisle_to_response(item.aisle, item.latest_job) for item in items]
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
        return status_response_from_result(result)
    except AisleNotFoundError:
        raise HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/cancel",
    status_code=202,
)
def cancel_aisle_job(
    inventory_id: str,
    aisle_id: str,
    job_id: str,
    use_case: CancelAisleJobUseCase = Depends(get_cancel_aisle_job_use_case),
) -> None:
    """Request cancellation of an active v3 process_aisle job.

    Cancellation is cooperative:
    - QUEUED jobs are marked CANCELED immediately (never started).
    - RUNNING jobs are marked CANCEL_REQUESTED; the executor will observe this and
      transition to CANCELED at the next safe checkpoint.
    """
    try:
        use_case.execute(
            CancelAisleJobCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                job_id=job_id,
            )
        )
    except AisleNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found or does not belong to this aisle/inventory")
    except ValueError as e:
        # Terminal or invalid state for cancellation.
        raise HTTPException(status_code=409, detail=str(e))


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/execution-log",
    response_model=ExecutionLogResponse,
)
def get_job_execution_log(
    inventory_id: str,
    aisle_id: str,
    job_id: str,
    job_repo: JobRepository = Depends(get_job_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
) -> ExecutionLogResponse:
    """Return structured execution log for a job (v3.1.1). Job must belong to this aisle and inventory."""
    job = job_repo.get_by_id(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.target_type != "aisle" or job.target_id != aisle_id:
        raise HTTPException(status_code=404, detail="Job not found or does not belong to this aisle")
    aisle = aisle_repo.get_by_id(aisle_id)
    if aisle is None or aisle.inventory_id != inventory_id:
        raise HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")
    run_dir = Path(load_settings().output_dir) / job_id / RUN_ID
    events = read_execution_log(run_dir)
    return ExecutionLogResponse(
        events=[ExecutionLogEvent.model_validate(e) for e in events],
    )
