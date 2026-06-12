"""v3 aisle CRUD, process, status, execution log."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response

from src.api.constants.error_wire import (
    HTTP_DETAIL_AISLE_NOT_FOUND_IN_INVENTORY,
    HTTP_DETAIL_EXPORT_PROVIDE_EXACTLY_ONE_OF_RUN_OR_COMPARE_JOBS,
    HTTP_DETAIL_JOB_NOT_FOUND,
    HTTP_DETAIL_JOB_NOT_IN_AISLE_CATEGORY_C,
    HTTP_DETAIL_JOB_NOT_IN_AISLE_INVENTORY,
    HTTP_DETAIL_ONLY_FORMAT_CSV_SUPPORTED,
)
from src.api.dependencies import (
    get_artifact_storage,
    get_cancel_aisle_job_use_case,
    get_compare_aisle_runs_use_case,
    get_compare_many_aisle_runs_use_case,
    get_create_aisle_use_case,
    get_export_aisle_benchmark_compare_csv_use_case,
    get_export_aisle_benchmark_run_csv_use_case,
    get_export_aisle_business_csv_use_case,
    get_export_aisle_results_csv_use_case,
    get_get_aisle_merge_results_use_case,
    get_get_aisle_processing_status_use_case,
    get_job_stale_reconciler,
    get_list_aisle_jobs_use_case,
    get_list_aisles_with_status_use_case,
    get_promote_aisle_operational_job_use_case,
    get_resolve_aisle_job_for_inventory_read_use_case,
    get_retry_aisle_job_use_case,
    get_run_aisle_merge_use_case,
    get_run_auditability_service,
    get_start_aisle_processing_use_case,
)
from src.api.errors import reraise_if_mapped
from src.api.schemas.aisle_schemas import AisleResponse, CreateAisleRequest
from src.api.schemas.benchmark_schemas import (
    AisleBenchmarkCompareManyRequest,
    AisleBenchmarkCompareManyResponse,
    AisleBenchmarkCompareResponse,
    PromoteOperationalJobRequest,
    PromoteOperationalJobResponse,
)
from src.api.schemas.listing_schemas import PaginatedAisleListResponse, compute_total_pages
from src.api.schemas.merge_schemas import (
    MergeResultItemResponse,
    MergeResultsResponse,
    RunMergeResponse,
)
from src.api.schemas.processing_schemas import (
    AisleExecutionLogResponse,
    AisleJobsListResponse,
    AisleStatusResponse,
    ExecutionLogResponse,
    JobDetailResponse,
    JobSummary,
    ProcessAisleRequest,
    ProcessAisleResponse,
)
from src.api.services.v3_stored_artifact_access import (
    StoredArtifactAccessError,
    load_hybrid_report_json_for_api,
)
from src.application.errors import (
    ActiveJobExistsError,
    AisleNotFoundError,
    ClientSupplierClientMismatchError,
    ClientSupplierNotFoundError,
    ClientSupplierRequiredForAisleError,
    DuplicateAisleCodeError,
    InventoryClientRequiredForAisleError,
    InventoryNotFoundError,
    JobDoesNotBelongToAisleError,
    JobNotFoundError,
)
from src.application.services.aisle_aggregated_execution_log import (
    AGGREGATE_AISLE_EXECUTION_LOG_JOBS_LIMIT,
    aggregate_aisle_execution_log_payload,
)
from src.application.services.aisle_table_query_params import (
    build_aisle_table_query_from_route_params,
)
from src.application.services.execution_log_enrichment import (
    aisle_execution_log_attachment_filename,
    build_enriched_execution_log,
    execution_log_attachment_filename,
    format_execution_log_plaintext,
)
from src.application.services.job_stale_reconciler import JobStaleReconciler
from src.application.services.run_auditability_service import RunAuditabilityService
from src.application.use_cases.aisles.cancel_aisle_job import (
    CancelAisleJobCommand,
    CancelAisleJobUseCase,
)
from src.application.use_cases.aisles.create_aisle import CreateAisleCommand, CreateAisleUseCase
from src.application.use_cases.aisles.get_aisle_merge_results import (
    GetAisleMergeResultsCommand,
    GetAisleMergeResultsUseCase,
)
from src.application.use_cases.aisles.get_aisle_processing_status import (
    GetAisleProcessingStatusUseCase,
)
from src.application.use_cases.aisles.list_aisle_jobs import (
    ListAisleJobsCommand,
    ListAisleJobsUseCase,
)
from src.application.use_cases.aisles.list_aisles_with_status import ListAislesWithStatusUseCase
from src.application.use_cases.aisles.promote_aisle_operational_job import (
    PromoteAisleOperationalJobCommand,
    PromoteAisleOperationalJobUseCase,
)
from src.application.use_cases.aisles.resolve_aisle_job_for_inventory_read import (
    ResolveAisleJobForInventoryReadUseCase,
)
from src.application.use_cases.aisles.retry_aisle_job import (
    RetryAisleJobCommand,
    RetryAisleJobUseCase,
)
from src.application.use_cases.aisles.run_aisle_merge import (
    RunAisleMergeCommand,
    RunAisleMergeUseCase,
)
from src.application.use_cases.aisles.start_aisle_processing import (
    StartAisleProcessingCommand,
    StartAisleProcessingUseCase,
)
from src.application.use_cases.analytics.compare_aisle_runs import (
    CompareAisleRunsCommand,
    CompareAisleRunsUseCase,
)
from src.application.use_cases.analytics.compare_many_aisle_runs import (
    CompareManyAisleRunsCommand,
    CompareManyAisleRunsUseCase,
)
from src.application.use_cases.analytics.export_aisle_benchmark import (
    ExportAisleBenchmarkCompareCsvUseCase,
    ExportAisleBenchmarkRunCommand,
    ExportAisleBenchmarkRunCsvUseCase,
)
from src.application.use_cases.inventories.export_inventory_business import (
    ExportAisleBusinessCsvUseCase,
)
from src.application.use_cases.inventories.export_inventory_results import (
    ExportAisleResultsCsvUseCase,
)
from src.domain.jobs.entities import Job
from src.infrastructure.artifacts.stored_artifact_reader import read_execution_log_events_for_job

from .shared import aisle_to_response, job_to_detail, job_to_summary, status_response_from_result

logger = logging.getLogger(__name__)

router = APIRouter()


def _build_aisle_aggregated_execution_log_body(
    *,
    inventory_id: str,
    aisle_id: str,
    list_jobs_uc: ListAisleJobsUseCase,
    artifact_storage: Any,
) -> dict[str, Any]:
    """List jobs then merge per-job execution logs (artifact reads remain in API layer)."""
    try:
        result = list_jobs_uc.execute(
            ListAisleJobsCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                limit=AGGREGATE_AISLE_EXECUTION_LOG_JOBS_LIMIT,
            )
        )
    except (InventoryNotFoundError, AisleNotFoundError) as e:
        reraise_if_mapped(e)
        raise

    def try_read_events(job: Job) -> tuple[list[dict[str, Any]] | None, dict[str, Any]]:
        src: dict[str, Any] = {"job_id": job.id, "status": "ok", "detail": None}
        try:
            raw = read_execution_log_events_for_job(job, artifact_store=artifact_storage)
            return raw, src
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
            return None, src
        except Exception as e:
            src["status"] = "error"
            src["detail"] = str(e)[:2048]
            logger.exception("aisle_execution_log_unexpected job_id=%s", job.id)
            return None, src

    return aggregate_aisle_execution_log_payload(
        inventory_id=inventory_id,
        aisle_id=aisle_id,
        jobs=result.jobs,
        try_read_events=try_read_events,
        logger=logger,
    )


def _load_job_for_inventory_job_route(
    resolve_uc: ResolveAisleJobForInventoryReadUseCase,
    inventory_id: str,
    aisle_id: str,
    job_id: str,
) -> Job:
    """Resolve job id in inventory/aisle scope.

    Intentionally **not** delegated to :func:`reraise_if_mapped`: HTTP ``detail`` strings here
    are fixed phrases (``Job not found``, ``Job not found or does not belong to this aisle``)
    and differ from ``str(JobNotFoundError)`` / ``str(JobDoesNotBelongToAisleError)`` used
    elsewhere — preserves Phase 6 regression contract in ``test_aisles_v3_wiring``.
    Same exception classes can yield **structured** JSON when mapped later on other routes;
    see **Known dual-shape (same exception class)** in :mod:`src.api.errors.error_mapping`.
    """
    try:
        return resolve_uc.execute(inventory_id, aisle_id, job_id)
    except JobNotFoundError:
        raise HTTPException(status_code=404, detail=HTTP_DETAIL_JOB_NOT_FOUND) from None
    except JobDoesNotBelongToAisleError:
        raise HTTPException(
            status_code=404,
            detail=HTTP_DETAIL_JOB_NOT_IN_AISLE_CATEGORY_C,
        ) from None
    except AisleNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=HTTP_DETAIL_AISLE_NOT_FOUND_IN_INVENTORY,
        ) from None


@router.post("/{inventory_id}/aisles", response_model=AisleResponse, status_code=201)
def create_aisle(
    inventory_id: str,
    payload: CreateAisleRequest,
    use_case: CreateAisleUseCase = Depends(get_create_aisle_use_case),
) -> AisleResponse:
    """Create an aisle in an inventory (v3.0). Returns 404 if inventory not found, 409 if code duplicate."""
    try:
        aisle = use_case.execute(
            CreateAisleCommand(
                inventory_id=inventory_id,
                code=payload.code,
                client_supplier_id=payload.client_supplier_id,
            )
        )
        return aisle_to_response(aisle)
    except (
        InventoryNotFoundError,
        DuplicateAisleCodeError,
        ClientSupplierNotFoundError,
        ClientSupplierRequiredForAisleError,
        InventoryClientRequiredForAisleError,
        ClientSupplierClientMismatchError,
    ) as e:
        reraise_if_mapped(e)
        raise


@router.get("/{inventory_id}/aisles", response_model=PaginatedAisleListResponse)
def list_aisles(
    inventory_id: str,
    use_case: ListAislesWithStatusUseCase = Depends(get_list_aisles_with_status_use_case),
    search: str | None = Query(None, description="Case-insensitive substring on aisle code."),
    status: str | None = Query(None, description="Exact aisle status (wire value)."),
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
        q = build_aisle_table_query_from_route_params(
            search=search,
            status=status,
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
    except InventoryNotFoundError as e:
        reraise_if_mapped(e)
        raise


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/process",
    response_model=ProcessAisleResponse,
    status_code=202,
)
def start_aisle_processing(
    inventory_id: str,
    aisle_id: str,
    payload: ProcessAisleRequest | None = Body(None),
    use_case: StartAisleProcessingUseCase = Depends(get_start_aisle_processing_use_case),
) -> ProcessAisleResponse:
    try:
        body = payload or ProcessAisleRequest(
            provider_name=None,
            model_name=None,
            prompt_key=None,
        )
        job_id = use_case.execute(
            StartAisleProcessingCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                resolve_execution_keys=True,
                requested_provider_name=body.provider_name,
                requested_model_name=body.model_name,
                requested_prompt_key=body.prompt_key,
            )
        )
        return ProcessAisleResponse(job_id=job_id)
    except Exception as e:
        reraise_if_mapped(e)
        raise


@router.get("/{inventory_id}/aisles/{aisle_id}/status", response_model=AisleStatusResponse)
def get_aisle_status(
    inventory_id: str,
    aisle_id: str,
    use_case: GetAisleProcessingStatusUseCase = Depends(get_get_aisle_processing_status_use_case),
) -> AisleStatusResponse:
    try:
        result = use_case.execute(inventory_id, aisle_id)
        return status_response_from_result(result)
    except AisleNotFoundError as e:
        reraise_if_mapped(e)
        raise


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
                job_to_summary(j, is_operational=(op is not None and op == j.id))
                for j in result.jobs
            ],
        )
    except (InventoryNotFoundError, AisleNotFoundError) as e:
        reraise_if_mapped(e)
        raise


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
    body = _build_aisle_aggregated_execution_log_body(
        inventory_id=inventory_id,
        aisle_id=aisle_id,
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
    body = _build_aisle_aggregated_execution_log_body(
        inventory_id=inventory_id,
        aisle_id=aisle_id,
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
        raise HTTPException(status_code=404, detail=HTTP_DETAIL_JOB_NOT_IN_AISLE_INVENTORY)
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
        raise HTTPException(status_code=404, detail=HTTP_DETAIL_JOB_NOT_IN_AISLE_INVENTORY)
    except (ActiveJobExistsError, ValueError) as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}",
    response_model=JobDetailResponse,
)
def get_aisle_job_detail(
    inventory_id: str,
    aisle_id: str,
    job_id: str,
    resolve_uc: ResolveAisleJobForInventoryReadUseCase = Depends(
        get_resolve_aisle_job_for_inventory_read_use_case
    ),
    stale_reconciler: JobStaleReconciler = Depends(get_job_stale_reconciler),
) -> JobDetailResponse:
    job = _load_job_for_inventory_job_route(resolve_uc, inventory_id, aisle_id, job_id)
    reconciled = stale_reconciler.reconcile(job)
    if reconciled is None:
        raise HTTPException(status_code=404, detail=HTTP_DETAIL_JOB_NOT_FOUND)
    return job_to_detail(reconciled)


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/execution-log",
    response_model=ExecutionLogResponse,
)
def get_job_execution_log(
    inventory_id: str,
    aisle_id: str,
    job_id: str,
    resolve_uc: ResolveAisleJobForInventoryReadUseCase = Depends(
        get_resolve_aisle_job_for_inventory_read_use_case
    ),
    artifact_storage=Depends(get_artifact_storage),
) -> ExecutionLogResponse:
    """Structured execution log for this job row; JSONL may cite other ``payload.job_id`` values (envelope + derived fields)."""
    job = _load_job_for_inventory_job_route(resolve_uc, inventory_id, aisle_id, job_id)
    try:
        raw_events = read_execution_log_events_for_job(job, artifact_store=artifact_storage)
    except StoredArtifactAccessError as e:
        logger.warning(
            "execution_log_http_error job_id=%s reason=%s detail=%s",
            job_id,
            e.reason_code,
            e.detail,
        )
        reraise_if_mapped(e, cause=e)
        raise
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
    resolve_uc: ResolveAisleJobForInventoryReadUseCase = Depends(
        get_resolve_aisle_job_for_inventory_read_use_case
    ),
    artifact_storage=Depends(get_artifact_storage),
) -> Response:
    """Plain-text execution log for download (same artifact as JSON execution-log)."""
    job = _load_job_for_inventory_job_route(resolve_uc, inventory_id, aisle_id, job_id)
    try:
        raw_events = read_execution_log_events_for_job(job, artifact_store=artifact_storage)
    except StoredArtifactAccessError as e:
        logger.warning(
            "execution_log_txt_http_error job_id=%s reason=%s detail=%s",
            job_id,
            e.reason_code,
            e.detail,
        )
        reraise_if_mapped(e, cause=e)
        raise
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
    resolve_uc: ResolveAisleJobForInventoryReadUseCase = Depends(
        get_resolve_aisle_job_for_inventory_read_use_case
    ),
    artifact_storage=Depends(get_artifact_storage),
) -> dict[str, Any]:
    """Return pipeline hybrid_report.json (dict) from durable artifact metadata or legacy disk."""
    job = _load_job_for_inventory_job_route(resolve_uc, inventory_id, aisle_id, job_id)
    try:
        return load_hybrid_report_json_for_api(job, artifact_store=artifact_storage)
    except StoredArtifactAccessError as e:
        logger.warning(
            "hybrid_report_http_error job_id=%s reason=%s detail=%s",
            job_id,
            e.reason_code,
            e.detail,
        )
        reraise_if_mapped(e, cause=e)
        raise


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/auditability",
)
def get_job_run_auditability(
    inventory_id: str,
    aisle_id: str,
    job_id: str,
    resolve_uc: ResolveAisleJobForInventoryReadUseCase = Depends(
        get_resolve_aisle_job_for_inventory_read_use_case
    ),
    audit_svc: RunAuditabilityService = Depends(get_run_auditability_service),
) -> dict[str, Any]:
    """Aggregated run observability (Phase H): job row, joins, ``result_json``, hybrid_report, execution_log."""
    _load_job_for_inventory_job_route(resolve_uc, inventory_id, aisle_id, job_id)
    view = audit_svc.build(job_id)
    if view is None:
        raise HTTPException(status_code=404, detail=HTTP_DETAIL_JOB_NOT_FOUND)
    return view.to_jsonable()


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
    except Exception as e:
        reraise_if_mapped(e)
        if isinstance(e, ValueError):
            raise HTTPException(status_code=422, detail=str(e)) from e
        raise


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/merge-results",
    response_model=MergeResultsResponse,
)
def get_aisle_merge_results(
    inventory_id: str,
    aisle_id: str,
    job_id: str | None = Query(
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
    except Exception as e:
        reraise_if_mapped(e)
        raise


@router.get("/{inventory_id}/aisles/{aisle_id}/export")
def export_aisle_results_csv(
    inventory_id: str,
    aisle_id: str,
    export_format: str = Query("csv", alias="format", description="Only csv supported."),
    profile: str = Query(
        "legacy",
        description="Export column profile: legacy (default, unchanged) or business (Spanish headers).",
    ),
    technical: bool = Query(
        False,
        description="When true, export the technical snapshot CSV (same contract as inventory export).",
    ),
    job_id: str | None = Query(
        None,
        description=(
            "Optional inventory job id. Omitted: same resolver as GET …/positions (operational or legacy). "
            "When set, export that run's slice for this aisle only."
        ),
    ),
    use_case: ExportAisleResultsCsvUseCase = Depends(get_export_aisle_results_csv_use_case),
    business_use_case: ExportAisleBusinessCsvUseCase = Depends(get_export_aisle_business_csv_use_case),
) -> Response:
    """Download this aisle's consolidated results CSV — **same columns and slice rules** as GET …/positions.

    Differs from ``GET /inventories/{id}/export`` (all aisles, operational slice each): this endpoint is
    scoped to one aisle and accepts an optional ``job_id`` to match the run visible in Aisle Results.
    """
    if (export_format or "").strip().lower() != "csv":
        raise HTTPException(status_code=422, detail=HTTP_DETAIL_ONLY_FORMAT_CSV_SUPPORTED)
    prof = (profile or "legacy").strip().lower()
    jid = job_id.strip() if job_id and str(job_id).strip() else None
    try:
        if prof == "business" and not technical:
            body, fname = business_use_case.execute_csv(
                inventory_id,
                aisle_id,
                job_id=jid,
            )
        elif prof in ("legacy", ""):
            body = use_case.execute_csv(
                inventory_id,
                aisle_id,
                job_id=jid,
                technical=technical,
            )
            suffix = "technical" if technical else "results"
            fname = f"inventory_{inventory_id}_aisle_{aisle_id}_{suffix}.csv"
        else:
            raise HTTPException(status_code=422, detail="profile must be legacy or business")
    except HTTPException:
        raise
    except Exception as e:
        reraise_if_mapped(e)
        raise
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

    **Product note:** the web app no longer exposes a standalone A/B comparison screen; operators use
    ``benchmark/compare-many``. This pairwise GET remains for exports, API consumers, and shared
    compare logic used by compare-many.
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
    except Exception as e:
        reraise_if_mapped(e)
        raise


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/benchmark/compare-many",
    response_model=AisleBenchmarkCompareManyResponse,
)
def compare_many_aisle_benchmark_runs(
    inventory_id: str,
    aisle_id: str,
    body: AisleBenchmarkCompareManyRequest = Body(...),
    use_case: CompareManyAisleRunsUseCase = Depends(get_compare_many_aisle_runs_use_case),
) -> AisleBenchmarkCompareManyResponse:
    """Phase 1/2 — baseline-centric compare-many for 2-3 explicit benchmark runs.

    TODO(analytics-parity): mirror this endpoint under the analytics alias when scope/risk allows.
    Deferred intentionally to keep this rollout narrow and low-risk.
    """
    try:
        payload = use_case.execute(
            CompareManyAisleRunsCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                job_ids=list(body.job_ids),
                baseline_job_id=body.baseline_job_id,
                include_diff_rows=bool(body.include_diff_rows),
                max_diff_rows=body.max_diff_rows,
            )
        )
        return AisleBenchmarkCompareManyResponse.model_validate(payload)
    except Exception as e:
        reraise_if_mapped(e)
        raise


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/promote-operational",
    response_model=PromoteOperationalJobResponse,
)
def promote_aisle_operational_job(
    inventory_id: str,
    aisle_id: str,
    body: PromoteOperationalJobRequest,
    use_case: PromoteAisleOperationalJobUseCase = Depends(
        get_promote_aisle_operational_job_use_case
    ),
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
    except Exception as e:
        reraise_if_mapped(e)
        raise


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
    run_exporter: ExportAisleBenchmarkRunCsvUseCase = Depends(
        get_export_aisle_benchmark_run_csv_use_case
    ),
    compare_exporter: ExportAisleBenchmarkCompareCsvUseCase = Depends(
        get_export_aisle_benchmark_compare_csv_use_case
    ),
) -> Response:
    """Benchmark-only CSV (extra columns). Operational aisle export: ``GET …/aisles/{aisle_id}/export``."""
    if (export_format or "").strip().lower() != "csv":
        raise HTTPException(status_code=422, detail=HTTP_DETAIL_ONLY_FORMAT_CSV_SUPPORTED)
    has_run = bool(run_job_id and str(run_job_id).strip())
    has_pair = bool(job_a_id and str(job_a_id).strip() and job_b_id and str(job_b_id).strip())
    if has_run == has_pair:
        raise HTTPException(
            status_code=422,
            detail=HTTP_DETAIL_EXPORT_PROVIDE_EXACTLY_ONE_OF_RUN_OR_COMPARE_JOBS,
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
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return Response(
        content=csv_body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
