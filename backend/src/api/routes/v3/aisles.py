"""v3 aisle CRUD, process, status, execution log."""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from src.api.dependencies import (
    get_artifact_storage,
    get_create_aisle_use_case,
    get_list_aisles_with_status_use_case,
    get_start_aisle_processing_use_case,
    get_get_aisle_processing_status_use_case,
    get_job_stale_reconciler,
    get_cancel_aisle_job_use_case,
    get_retry_aisle_job_use_case,
    get_aisle_repo,
    get_get_aisle_merge_results_use_case,
    get_job_repo,
    get_run_aisle_merge_use_case,
)
from src.api.services.v3_stored_artifact_access import (
    StoredArtifactAccessError,
    load_hybrid_report_json_for_api,
    read_execution_log_events_for_job,
)
from src.api.schemas.merge_schemas import (
    MergeResultItemResponse,
    MergeResultsResponse,
    RunMergeResponse,
)
from src.api.schemas.aisle_schemas import AisleResponse, CreateAisleRequest
from src.api.schemas.listing_schemas import PaginatedAisleListResponse, compute_total_pages
from src.application.ports.contracts import AisleTableQuery
from src.api.schemas.processing_schemas import (
    AisleStatusResponse,
    ExecutionLogEvent,
    ExecutionLogResponse,
    JobSummary,
    ProcessAisleResponse,
)
from src.application.ports.repositories import AisleRepository, JobRepository
from src.application.errors import AisleNotFoundError, ActiveJobExistsError, DuplicateAisleCodeError, InventoryNotFoundError
from src.application.use_cases.create_aisle import CreateAisleCommand, CreateAisleUseCase
from src.application.use_cases.list_aisles_with_status import ListAislesWithStatusUseCase
from src.application.use_cases.start_aisle_processing import StartAisleProcessingCommand, StartAisleProcessingUseCase
from src.application.use_cases.get_aisle_processing_status import GetAisleProcessingStatusUseCase
from src.application.use_cases.cancel_aisle_job import CancelAisleJobCommand, CancelAisleJobUseCase
from src.application.use_cases.retry_aisle_job import RetryAisleJobCommand, RetryAisleJobUseCase
from src.application.services.job_stale_reconciler import JobStaleReconciler
from src.application.use_cases.get_aisle_merge_results import (
    GetAisleMergeResultsCommand,
    GetAisleMergeResultsUseCase,
)
from src.application.use_cases.run_aisle_merge import (
    RunAisleMergeCommand,
    RunAisleMergeUseCase,
)
from .shared import aisle_to_response, job_to_summary, status_response_from_result

logger = logging.getLogger(__name__)

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


@router.get("/{inventory_id}/aisles", response_model=PaginatedAisleListResponse)
def list_aisles(
    inventory_id: str,
    use_case: ListAislesWithStatusUseCase = Depends(get_list_aisles_with_status_use_case),
    search: Optional[str] = Query(None, description="Case-insensitive substring on aisle code."),
    status: Optional[str] = Query(None, description="Exact aisle status (wire value)."),
    sort_by: str = Query(
        "code",
        description=(
            "code | status | last_activity_at | pending_review_positions_count | "
            "positions_count | assets_count"
        ),
    ),
    sort_dir: str = Query("asc", description="asc | desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> PaginatedAisleListResponse:
    """List aisles for an inventory with rollups, optional search/filter/sort/pagination (Sprint 1.4).

    **Contract:** returns a **paginated object** (`items`, `page`, `page_size`, `total_items`,
    `total_pages`), not a JSON array. Intentional breaking change from the pre–1.4 array body.
    """
    try:
        q = AisleTableQuery(
            search=search.strip() if search and search.strip() else None,
            status=status.strip() if status and str(status).strip() else None,
            sort_by=sort_by,
            sort_dir=sort_dir,
            page=page,
            page_size=page_size,
        )
        items, total = use_case.execute(inventory_id, q)
        ps = q.page_size
        return PaginatedAisleListResponse(
            items=[
                aisle_to_response(
                    item.aisle,
                    item.latest_job,
                    assets_count=item.assets_count,
                    positions_count=item.positions_count,
                    pending_review_positions_count=item.pending_review_positions_count,
                    last_activity_at=item.last_activity_at,
                )
                for item in items
            ],
            page=q.page,
            page_size=ps,
            total_items=total,
            total_pages=compute_total_pages(total, ps),
        )
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
    response_model=JobSummary,
    status_code=202,
)
def cancel_aisle_job(
    inventory_id: str,
    aisle_id: str,
    job_id: str,
    use_case: CancelAisleJobUseCase = Depends(get_cancel_aisle_job_use_case),
) -> JobSummary:
    """Request cancellation of an active v3 process_aisle job.

    Cancellation is cooperative:
    - QUEUED jobs are marked CANCELED immediately (never started).
    - RUNNING jobs are marked CANCEL_REQUESTED; the executor will observe this and
      transition to CANCELED at the next safe checkpoint.
    """
    try:
        job = use_case.execute(
            CancelAisleJobCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                job_id=job_id,
            )
        )
        return job_to_summary(job)
    except AisleNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found or does not belong to this aisle/inventory")
    except ValueError as e:
        # Terminal or invalid state for cancellation.
        raise HTTPException(status_code=409, detail=str(e))


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/retry",
    response_model=JobSummary,
    status_code=202,
)
def retry_aisle_job(
    inventory_id: str,
    aisle_id: str,
    job_id: str,
    use_case: RetryAisleJobUseCase = Depends(get_retry_aisle_job_use_case),
) -> JobSummary:
    try:
        job = use_case.execute(
            RetryAisleJobCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                job_id=job_id,
            )
        )
        return job_to_summary(job)
    except AisleNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found or does not belong to this aisle/inventory")
    except (ActiveJobExistsError, ValueError) as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}",
    response_model=JobSummary,
)
def get_aisle_job_detail(
    inventory_id: str,
    aisle_id: str,
    job_id: str,
    job_repo: JobRepository = Depends(get_job_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    stale_reconciler: JobStaleReconciler = Depends(get_job_stale_reconciler),
) -> JobSummary:
    job = job_repo.get_by_id(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.target_type != "aisle" or job.target_id != aisle_id:
        raise HTTPException(status_code=404, detail="Job not found or does not belong to this aisle")
    aisle = aisle_repo.get_by_id(aisle_id)
    if aisle is None or aisle.inventory_id != inventory_id:
        raise HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")
    job = stale_reconciler.reconcile(job)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job_to_summary(job)


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
    artifact_storage=Depends(get_artifact_storage),
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
    try:
        raw_events = read_execution_log_events_for_job(job, artifact_store=artifact_storage)
    except StoredArtifactAccessError as e:
        logger.warning(
            "execution_log_http_error job_id=%s reason=%s detail=%s",
            job_id,
            e.reason_code,
            e.detail,
        )
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
    return ExecutionLogResponse(
        events=[ExecutionLogEvent.model_validate(e) for e in raw_events],
    )


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/hybrid-report",
)
def get_job_hybrid_report(
    inventory_id: str,
    aisle_id: str,
    job_id: str,
    job_repo: JobRepository = Depends(get_job_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    artifact_storage=Depends(get_artifact_storage),
) -> dict[str, Any]:
    """Return pipeline hybrid_report.json (dict) from durable artifact metadata or legacy disk."""
    job = job_repo.get_by_id(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.target_type != "aisle" or job.target_id != aisle_id:
        raise HTTPException(status_code=404, detail="Job not found or does not belong to this aisle")
    aisle = aisle_repo.get_by_id(aisle_id)
    if aisle is None or aisle.inventory_id != inventory_id:
        raise HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")
    try:
        return load_hybrid_report_json_for_api(job, artifact_store=artifact_storage)
    except StoredArtifactAccessError as e:
        logger.warning(
            "hybrid_report_http_error job_id=%s reason=%s detail=%s",
            job_id,
            e.reason_code,
            e.detail,
        )
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/merge",
    response_model=RunMergeResponse,
    status_code=202,
)
def run_aisle_merge(
    inventory_id: str,
    aisle_id: str,
    use_case: RunAisleMergeUseCase = Depends(get_run_aisle_merge_use_case),
) -> RunMergeResponse:
    """Run merge/consolidation artifact recompute (non-authoritative, post-process).

    Compatibility note:
    - `product_records_updated` is returned for backward compatibility.
    - In `artifact_only` mode, it is expected to remain 0.
    """
    try:
        result = use_case.execute(
            RunAisleMergeCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
            )
        )
        return RunMergeResponse(
            operation_mode="artifact_only",
            authoritative_quantity_updated=False,
            raw_count=result.raw_count,
            normalized_count=result.normalized_count,
            final_count=result.final_count,
            product_records_updated=result.product_records_updated,
        )
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail="Inventory not found")
    except AisleNotFoundError:
        raise HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/merge-results",
    response_model=MergeResultsResponse,
)
def get_aisle_merge_results(
    inventory_id: str,
    aisle_id: str,
    use_case: GetAisleMergeResultsUseCase = Depends(get_get_aisle_merge_results_use_case),
) -> MergeResultsResponse:
    try:
        records = use_case.execute(
            GetAisleMergeResultsCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
            )
        )
        return MergeResultsResponse(
            results=[
                MergeResultItemResponse(
                    id=r.id,
                    position_id=r.position_id,
                    sku=r.sku,
                    product_name=r.product_name,
                    merged_quantity=r.quantity,
                    normalized_label_ids=list(r.normalized_label_ids),
                    review_required=r.review_required,
                    explanation_summary=r.explanation_summary,
                    metadata=dict(r.metadata or {}),
                    created_at=r.created_at.isoformat(),
                )
                for r in records
            ]
        )
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail="Inventory not found")
    except AisleNotFoundError:
        raise HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")
