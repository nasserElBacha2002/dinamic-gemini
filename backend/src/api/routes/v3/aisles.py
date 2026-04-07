"""v3 aisle CRUD, process, status, execution log."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
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
    get_list_aisle_jobs_use_case,
    get_job_repo,
    get_run_aisle_merge_use_case,
    get_compare_aisle_runs_use_case,
    get_promote_aisle_operational_job_use_case,
    get_export_aisle_benchmark_run_csv_use_case,
    get_export_aisle_benchmark_compare_csv_use_case,
    get_export_aisle_results_csv_use_case,
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
from src.api.schemas.benchmark_schemas import (
    AisleBenchmarkCompareResponse,
    PromoteOperationalJobRequest,
    PromoteOperationalJobResponse,
)
from src.application.services.execution_log_enrichment import (
    aisle_execution_log_attachment_filename,
    build_enriched_aisle_aggregated_execution_log,
    build_enriched_execution_log,
    execution_log_attachment_filename,
    format_execution_log_plaintext,
    merge_raw_execution_log_events_by_ts,
)
from src.api.schemas.processing_schemas import (
    AisleExecutionLogResponse,
    AisleJobsListResponse,
    AisleStatusResponse,
    ExecutionLogResponse,
    JobSummary,
    ProcessAisleRequest,
    ProcessAisleResponse,
)
from src.application.ports.repositories import AisleRepository, JobRepository
from src.application.errors import (
    AisleNotFoundError,
    ActiveJobExistsError,
    BenchmarkCompareJobsMustDifferError,
    DuplicateAisleCodeError,
    InventoryNotFoundError,
    JobDoesNotBelongToAisleError,
    JobNotFoundError,
    JobPromotionNotAllowedError,
    InvalidProcessingModelError,
    InvalidProcessingPromptKeyError,
    ProcessingProviderNotConfiguredError,
    UnknownProcessingProviderError,
)
from src.application.services.processing_provider_resolution import resolve_start_processing_request
from src.config import load_settings
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
from src.application.use_cases.compare_aisle_runs import CompareAisleRunsCommand, CompareAisleRunsUseCase
from src.application.use_cases.export_aisle_benchmark import (
    ExportAisleBenchmarkCompareCsvUseCase,
    ExportAisleBenchmarkRunCommand,
    ExportAisleBenchmarkRunCsvUseCase,
)
from src.application.use_cases.export_inventory_results import ExportAisleResultsCsvUseCase
from src.application.use_cases.list_aisle_jobs import ListAisleJobsCommand, ListAisleJobsUseCase
from src.domain.jobs.entities import Job
from src.application.use_cases.promote_aisle_operational_job import (
    PromoteAisleOperationalJobCommand,
    PromoteAisleOperationalJobUseCase,
)
from src.application.use_cases.run_aisle_merge import (
    RunAisleMergeCommand,
    RunAisleMergeUseCase,
)
from .shared import aisle_to_response, job_to_summary, status_response_from_result

logger = logging.getLogger(__name__)

router = APIRouter()

_AGGREGATE_AISLE_EXECUTION_LOG_JOBS_LIMIT = 500


def _job_to_execution_log_row(job: Job) -> Dict[str, Any]:
    return {
        "job_id": job.id,
        "provider_name": job.provider_name,
        "model_name": job.model_name,
        "prompt_key": job.prompt_key,
        "prompt_version": job.prompt_version,
        "execution_id": job.execution_id,
    }


def _aggregate_aisle_execution_log_payload(
    inventory_id: str,
    aisle_id: str,
    *,
    list_jobs_uc: ListAisleJobsUseCase,
    artifact_storage: Any,
) -> Dict[str, Any]:
    try:
        result = list_jobs_uc.execute(
            ListAisleJobsCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                limit=_AGGREGATE_AISLE_EXECUTION_LOG_JOBS_LIMIT,
            )
        )
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail="Inventory not found")
    except AisleNotFoundError:
        raise HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")

    log_sources: List[Dict[str, Any]] = []
    streams: List[Tuple[str, datetime, List[Dict[str, Any]]]] = []

    for job in result.jobs:
        src: Dict[str, Any] = {"job_id": job.id, "status": "ok", "detail": None}
        try:
            raw = read_execution_log_events_for_job(job, artifact_store=artifact_storage)
            streams.append((job.id, job.created_at, raw))
        except StoredArtifactAccessError as e:
            if int(e.status_code) == 404:
                src["status"] = "missing"
            else:
                src["status"] = "error"
            src["detail"] = str(e.detail)[:2048]
            logger.warning(
                "aisle_execution_log_skip job_id=%s reason=%s detail=%s",
                job.id,
                e.reason_code,
                e.detail,
            )
        except Exception as e:
            src["status"] = "error"
            src["detail"] = str(e)[:2048]
            logger.exception("aisle_execution_log_unexpected job_id=%s", job.id)
        log_sources.append(src)

    merged_events, owners = merge_raw_execution_log_events_by_ts(streams)
    seed_ids = [j.id for j in result.jobs]
    jobs_meta = [_job_to_execution_log_row(j) for j in result.jobs]
    return build_enriched_aisle_aggregated_execution_log(
        inventory_id=inventory_id,
        aisle_id=aisle_id,
        raw_events=merged_events,
        artifact_owner_job_ids=owners,
        seed_job_ids=seed_ids,
        jobs=jobs_meta,
        log_sources=log_sources,
    )


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
    payload: ProcessAisleRequest | None = Body(None),
    use_case: StartAisleProcessingUseCase = Depends(get_start_aisle_processing_use_case),
) -> ProcessAisleResponse:
    try:
        body = payload or ProcessAisleRequest()
        settings = load_settings()
        pipeline_key, model_name, prompt_key = resolve_start_processing_request(
            requested_provider_name=body.provider_name,
            requested_model_name=body.model_name,
            requested_prompt_key=body.prompt_key,
            settings=settings,
        )
        job_id = use_case.execute(
            StartAisleProcessingCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                pipeline_provider_key=pipeline_key,
                model_name=model_name,
                prompt_key=prompt_key,
            )
        )
        return ProcessAisleResponse(job_id=job_id)
    except UnknownProcessingProviderError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except InvalidProcessingModelError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except InvalidProcessingPromptKeyError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ProcessingProviderNotConfiguredError as e:
        raise HTTPException(status_code=422, detail=str(e))
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


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/jobs",
    response_model=AisleJobsListResponse,
)
def list_aisle_jobs(
    inventory_id: str,
    aisle_id: str,
    limit: int = Query(50, ge=1, le=500, description="Max jobs to return (newest first)."),
    use_case: ListAisleJobsUseCase = Depends(get_list_aisle_jobs_use_case),
) -> AisleJobsListResponse:
    """List process_aisle jobs for an aisle (newest first) for run browsing / future UI selector."""
    try:
        result = use_case.execute(
            ListAisleJobsCommand(inventory_id=inventory_id, aisle_id=aisle_id, limit=limit)
        )
        op = result.operational_job_id
        return AisleJobsListResponse(
            operational_job_id=op,
            jobs=[
                job_to_summary(j, is_operational=(op is not None and op == j.id)) for j in result.jobs
            ],
        )
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail="Inventory not found")
    except AisleNotFoundError:
        raise HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/execution-log",
    response_model=AisleExecutionLogResponse,
)
def get_aisle_aggregated_execution_log(
    inventory_id: str,
    aisle_id: str,
    list_jobs_uc: ListAisleJobsUseCase = Depends(get_list_aisle_jobs_use_case),
    artifact_storage=Depends(get_artifact_storage),
) -> AisleExecutionLogResponse:
    """Merge execution logs from all jobs listed for this aisle (up to limit); per-job read failures are non-fatal."""
    body = _aggregate_aisle_execution_log_payload(
        inventory_id,
        aisle_id,
        list_jobs_uc=list_jobs_uc,
        artifact_storage=artifact_storage,
    )
    return AisleExecutionLogResponse.model_validate(body)


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/execution-log.txt",
    response_class=Response,
)
def get_aisle_aggregated_execution_log_txt(
    inventory_id: str,
    aisle_id: str,
    list_jobs_uc: ListAisleJobsUseCase = Depends(get_list_aisle_jobs_use_case),
    artifact_storage=Depends(get_artifact_storage),
) -> Response:
    """Plain-text merged execution log for all aisle jobs (UTF-8 download)."""
    body = _aggregate_aisle_execution_log_payload(
        inventory_id,
        aisle_id,
        list_jobs_uc=list_jobs_uc,
        artifact_storage=artifact_storage,
    )
    text = format_execution_log_plaintext(body["events"])
    filename = aisle_execution_log_attachment_filename(inventory_id, aisle_id)
    return Response(
        content=text.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
    """Structured execution log for this job row; JSONL may cite other ``payload.job_id`` values (envelope + derived fields)."""
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
    payload = build_enriched_execution_log(
        inventory_id=inventory_id,
        aisle_id=aisle_id,
        requested_job_id=job_id,
        raw_events=raw_events,
    )
    return ExecutionLogResponse.model_validate(payload)


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/execution-log.txt",
    response_class=Response,
)
def get_job_execution_log_txt(
    inventory_id: str,
    aisle_id: str,
    job_id: str,
    job_repo: JobRepository = Depends(get_job_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    artifact_storage=Depends(get_artifact_storage),
) -> Response:
    """Plain-text execution log for download (same artifact as JSON execution-log)."""
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
            "execution_log_txt_http_error job_id=%s reason=%s detail=%s",
            job_id,
            e.reason_code,
            e.detail,
        )
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
    body = build_enriched_execution_log(
        inventory_id=inventory_id,
        aisle_id=aisle_id,
        requested_job_id=job_id,
        raw_events=raw_events,
    )
    text = format_execution_log_plaintext(body["events"])
    filename = execution_log_attachment_filename(inventory_id, aisle_id, job_id)
    return Response(
        content=text.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
    job_id: str = Query(
        ...,
        min_length=1,
        description=(
            "Inventory job id for the run to merge (same as GET …/positions `result_job_id`), "
            "or the literal `legacy` for rows with `job_id IS NULL`."
        ),
    ),
    use_case: RunAisleMergeUseCase = Depends(get_run_aisle_merge_use_case),
) -> RunMergeResponse:
    """Run merge/consolidation as an explicit manual post-process scoped to one job slice."""
    try:
        result = use_case.execute(
            RunAisleMergeCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                job_id=job_id,
            )
        )
        return RunMergeResponse(
            operation_mode="manual_authoritative",
            authoritative_quantity_updated=result.product_records_updated > 0,
            raw_count=result.raw_count,
            normalized_count=result.normalized_count,
            final_count=result.final_count,
            product_records_updated=result.product_records_updated,
        )
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail="Inventory not found")
    except AisleNotFoundError:
        raise HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")
    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except JobDoesNotBelongToAisleError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/merge-results",
    response_model=MergeResultsResponse,
)
def get_aisle_merge_results(
    inventory_id: str,
    aisle_id: str,
    job_id: Optional[str] = Query(
        None,
        description="Optional inventory job id; omitted uses operational job or legacy slice (Phase 2).",
    ),
    use_case: GetAisleMergeResultsUseCase = Depends(get_get_aisle_merge_results_use_case),
) -> MergeResultsResponse:
    try:
        merge_result = use_case.execute(
            GetAisleMergeResultsCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                job_id=job_id.strip() if job_id and str(job_id).strip() else None,
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
                for r in merge_result.records
            ],
            result_job_id=merge_result.resolved_job_id,
            result_context_source=merge_result.result_context_source,
        )
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail="Inventory not found")
    except AisleNotFoundError:
        raise HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")
    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except JobDoesNotBelongToAisleError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/{inventory_id}/aisles/{aisle_id}/export")
def export_aisle_results_csv(
    inventory_id: str,
    aisle_id: str,
    export_format: str = Query("csv", alias="format", description="Only csv supported."),
    technical: bool = Query(
        False,
        description="When true, export the technical snapshot CSV (same contract as inventory export).",
    ),
    job_id: Optional[str] = Query(
        None,
        description=(
            "Optional inventory job id. Omitted: same resolver as GET …/positions (operational or legacy). "
            "When set, export that run's slice for this aisle only."
        ),
    ),
    use_case: ExportAisleResultsCsvUseCase = Depends(get_export_aisle_results_csv_use_case),
) -> Response:
    """Download this aisle's consolidated results CSV — **same columns and slice rules** as GET …/positions.

    Differs from ``GET /inventories/{id}/export`` (all aisles, operational slice each): this endpoint is
    scoped to one aisle and accepts an optional ``job_id`` to match the run visible in Aisle Results.
    """
    if (export_format or "").strip().lower() != "csv":
        raise HTTPException(status_code=422, detail="Only format=csv is supported")
    try:
        body = use_case.execute_csv(
            inventory_id,
            aisle_id,
            job_id=job_id.strip() if job_id and str(job_id).strip() else None,
            technical=technical,
        )
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail="Inventory not found")
    except AisleNotFoundError:
        raise HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")
    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except JobDoesNotBelongToAisleError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    suffix = "technical" if technical else "results"
    fname = f"inventory_{inventory_id}_aisle_{aisle_id}_{suffix}.csv"
    return Response(
        content=body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/benchmark/compare",
    response_model=AisleBenchmarkCompareResponse,
)
def compare_aisle_benchmark_runs(
    inventory_id: str,
    aisle_id: str,
    job_a_id: str = Query(..., alias="job_a_id", min_length=1),
    job_b_id: str = Query(..., alias="job_b_id", min_length=1),
    use_case: CompareAisleRunsUseCase = Depends(get_compare_aisle_runs_use_case),
) -> AisleBenchmarkCompareResponse:
    """Phase 6 — read-only compare metrics between two explicit runs (same aisle, same inventory).

    For **benchmark / inspection** only; does not alter operational analytics defaults.
    ``job_a_id`` and ``job_b_id`` must name two different runs.
    """
    try:
        payload = use_case.execute(
            CompareAisleRunsCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                job_a_id=job_a_id.strip(),
                job_b_id=job_b_id.strip(),
            )
        )
        return AisleBenchmarkCompareResponse.model_validate(payload)
    except BenchmarkCompareJobsMustDifferError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail="Inventory not found")
    except AisleNotFoundError:
        raise HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")
    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except JobDoesNotBelongToAisleError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/promote-operational",
    response_model=PromoteOperationalJobResponse,
)
def promote_aisle_operational_job(
    inventory_id: str,
    aisle_id: str,
    body: PromoteOperationalJobRequest,
    use_case: PromoteAisleOperationalJobUseCase = Depends(get_promote_aisle_operational_job_use_case),
) -> PromoteOperationalJobResponse:
    """Set ``aisles.operational_job_id`` to a succeeded process_aisle job; prior runs stay persisted."""
    try:
        jid = use_case.execute(
            PromoteAisleOperationalJobCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                job_id=body.job_id.strip(),
            )
        )
        return PromoteOperationalJobResponse(aisle_id=aisle_id, operational_job_id=jid)
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail="Inventory not found")
    except AisleNotFoundError:
        raise HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")
    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except JobDoesNotBelongToAisleError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except JobPromotionNotAllowedError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.get("/{inventory_id}/aisles/{aisle_id}/benchmark/export")
def export_aisle_benchmark(
    inventory_id: str,
    aisle_id: str,
    export_format: str = Query("csv", alias="format", description="Only csv supported."),
    run_job_id: str | None = Query(
        None,
        description="Single-run export: job slice with benchmark metadata columns appended.",
    ),
    job_a_id: str | None = Query(None, alias="job_a_id"),
    job_b_id: str | None = Query(None, alias="job_b_id"),
    run_exporter: ExportAisleBenchmarkRunCsvUseCase = Depends(get_export_aisle_benchmark_run_csv_use_case),
    compare_exporter: ExportAisleBenchmarkCompareCsvUseCase = Depends(
        get_export_aisle_benchmark_compare_csv_use_case
    ),
) -> Response:
    """Benchmark-only CSV (extra columns). Operational aisle export: ``GET …/aisles/{aisle_id}/export``."""
    if (export_format or "").strip().lower() != "csv":
        raise HTTPException(status_code=422, detail="Only format=csv is supported")
    has_run = bool(run_job_id and str(run_job_id).strip())
    has_pair = bool(job_a_id and str(job_a_id).strip() and job_b_id and str(job_b_id).strip())
    if has_run == has_pair:
        raise HTTPException(
            status_code=422,
            detail="Provide exactly one of: run_job_id (single-run export) or both job_a_id and job_b_id (compare export).",
        )
    try:
        if has_run:
            csv_body = run_exporter.execute_csv(
                ExportAisleBenchmarkRunCommand(
                    inventory_id=inventory_id,
                    aisle_id=aisle_id,
                    run_job_id=str(run_job_id).strip(),
                )
            )
            fname = f"benchmark_run_{inventory_id}_{aisle_id}_{str(run_job_id).strip()}.csv"
        else:
            csv_body = compare_exporter.execute_csv(
                CompareAisleRunsCommand(
                    inventory_id=inventory_id,
                    aisle_id=aisle_id,
                    job_a_id=str(job_a_id).strip(),
                    job_b_id=str(job_b_id).strip(),
                )
            )
            fname = (
                f"benchmark_compare_{inventory_id}_{aisle_id}_"
                f"{str(job_a_id).strip()}_{str(job_b_id).strip()}.csv"
            )
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail="Inventory not found")
    except AisleNotFoundError:
        raise HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")
    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except JobDoesNotBelongToAisleError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except BenchmarkCompareJobsMustDifferError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return Response(
        content=csv_body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
