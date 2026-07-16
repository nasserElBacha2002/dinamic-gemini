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
    get_activate_aisle_use_case,
    get_artifact_publication_outbox_store,
    get_artifact_storage,
    get_cancel_aisle_job_use_case,
    get_compare_aisle_runs_use_case,
    get_compare_many_aisle_runs_use_case,
    get_create_aisle_use_case,
    get_deactivate_aisle_use_case,
    get_export_aisle_benchmark_compare_csv_use_case,
    get_export_aisle_benchmark_run_csv_use_case,
    get_export_aisle_business_csv_use_case,
    get_export_aisle_results_csv_use_case,
    get_finalization_assessment_service,
    get_get_aisle_merge_results_use_case,
    get_get_aisle_processing_status_use_case,
    get_inventory_repo,
    get_job_artifact_catalog_service,
    get_job_retry_chain_service,
    get_job_stale_reconciler,
    get_list_aisle_jobs_use_case,
    get_list_aisles_with_status_use_case,
    get_promote_aisle_operational_job_use_case,
    get_resolve_aisle_job_for_inventory_read_use_case,
    get_result_evidence_query_service,
    get_retry_aisle_job_use_case,
    get_run_aisle_merge_use_case,
    get_run_auditability_service,
    get_start_aisle_processing_use_case,
    get_update_aisle_code_use_case,
)
from src.api.errors import reraise_if_mapped
from src.api.mappers.result_evidence_mapper import job_traceability_to_response
from src.api.schemas.aisle_schemas import AisleResponse, CreateAisleRequest, UpdateAisleRequest
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
from src.api.schemas.observability_job_schemas import (
    ArtifactPreviewResponse,
    CursorPageMeta,
    ExecutionLogFiltersMeta,
    ExecutionLogPageResponse,
    JobArtifactPageResponse,
    JobArtifactResponse,
    JobArtifactSourceResponse,
    JobErrorPageResponse,
    JobErrorResponse,
    JobRetryChainResponse,
    JobTimelineEventResponse,
    JobTimelinePageResponse,
    RetryChainAttemptResponse,
    RetryChainEdgeResponse,
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
from src.api.schemas.result_evidence_schemas import JobTraceabilityResponse
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
from src.application.ports.repositories import InventoryRepository
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
from src.application.services.execution_log_incremental import (
    InvalidCursorError,
    open_execution_log_tempfile,
    paginate_jsonl_stream,
)
from src.application.services.execution_log_ranged import (
    LogChangedError,
    paginate_execution_log_ranged,
    resolve_execution_log_meta,
)
from src.application.services.finalization_assessment_service import FinalizationAssessmentService
from src.application.services.job_artifact_catalog_service import (
    JobArtifactCatalogService,
    JobArtifactView,
    assert_job_owned_storage_key,
    resolve_artifact_download_filename,
)
from src.application.services.job_errors_service import collect_job_errors
from src.application.services.job_retry_chain_service import JobRetryChainService
from src.application.services.job_stale_reconciler import JobStaleReconciler
from src.application.services.job_timeline_service import (
    derive_timeline_events,
)
from src.application.services.observability_access import (
    CAP_CANCEL_RETRY,
    CAP_DOWNLOAD_ARTIFACTS,
    CAP_VIEW_ARTIFACT_PREVIEW,
    CAP_VIEW_STACK_TRACES,
    CAP_VIEW_SUMMARY,
    CAP_VIEW_TECHNICAL_LOGS,
    ObservabilityAccessContext,
    assert_inventory_client_scope,
    principal_has_capability,
)
from src.application.services.observability_download_gate import (
    acquire_download_slot,
    content_disposition_attachment,
)
from src.application.services.observability_output_sanitizer import (
    sanitize_execution_log_events,
    sanitize_observability_value,
)
from src.application.services.result_evidence_query_service import ResultEvidenceQueryService
from src.application.services.run_auditability_service import RunAuditabilityService
from src.application.use_cases.aisles.activate_aisle import (
    ActivateAisleCommand,
    ActivateAisleUseCase,
)
from src.application.use_cases.aisles.cancel_aisle_job import (
    CancelAisleJobCommand,
    CancelAisleJobUseCase,
)
from src.application.use_cases.aisles.create_aisle import CreateAisleCommand, CreateAisleUseCase
from src.application.use_cases.aisles.deactivate_aisle import (
    DeactivateAisleCommand,
    DeactivateAisleUseCase,
)
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
from src.application.use_cases.aisles.update_aisle_code import (
    UpdateAisleCodeCommand,
    UpdateAisleCodeUseCase,
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
from src.auth.dependencies import require_observability_capability
from src.auth.schemas import AuthUser
from src.config import load_settings
from src.domain.jobs.entities import Job
from src.infrastructure.artifacts.stored_artifact_reader import read_execution_log_events_for_job
from src.pipeline.secret_redaction import redact_secrets_in_text

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
    *,
    access_user: AuthUser | None = None,
) -> Job:
    """Resolve job id in inventory/aisle scope (optional company scope via ``access_user``).

    Intentionally **not** delegated to :func:`reraise_if_mapped`: HTTP ``detail`` strings here
    are fixed phrases (``Job not found``, ``Job not found or does not belong to this aisle``)
    and differ from ``str(JobNotFoundError)`` / ``str(JobDoesNotBelongToAisleError)`` used
    elsewhere — preserves Phase 6 regression contract in ``test_aisles_v3_wiring``.
    Same exception classes can yield **structured** JSON when mapped later on other routes;
    see **Known dual-shape (same exception class)** in :mod:`src.api.errors.error_mapping`.
    """
    try:
        return resolve_uc.execute(
            inventory_id, aisle_id, job_id, access_user=access_user
        )
    except InventoryNotFoundError:
        # Prefer 404 without revealing cross-company inventory existence.
        raise HTTPException(status_code=404, detail=HTTP_DETAIL_JOB_NOT_FOUND) from None
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


@router.patch(
    "/{inventory_id}/aisles/{aisle_id}",
    response_model=AisleResponse,
)
def update_aisle_code(
    inventory_id: str,
    aisle_id: str,
    payload: UpdateAisleRequest,
    use_case: UpdateAisleCodeUseCase = Depends(get_update_aisle_code_use_case),
) -> AisleResponse:
    """Rename an aisle code within an inventory. Returns 404 if missing, 409 if code duplicate."""
    try:
        aisle = use_case.execute(
            UpdateAisleCodeCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                code=payload.code,
            )
        )
        return aisle_to_response(aisle)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except (AisleNotFoundError, DuplicateAisleCodeError) as e:
        reraise_if_mapped(e)
        raise


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/deactivate",
    response_model=AisleResponse,
)
def deactivate_aisle(
    inventory_id: str,
    aisle_id: str,
    use_case: DeactivateAisleUseCase = Depends(get_deactivate_aisle_use_case),
) -> AisleResponse:
    """Soft-deactivate an aisle. Blocked while an active process job exists (409)."""
    try:
        aisle = use_case.execute(
            DeactivateAisleCommand(inventory_id=inventory_id, aisle_id=aisle_id)
        )
        return aisle_to_response(aisle)
    except (AisleNotFoundError, ActiveJobExistsError) as e:
        reraise_if_mapped(e)
        raise


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/activate",
    response_model=AisleResponse,
)
def activate_aisle(
    inventory_id: str,
    aisle_id: str,
    use_case: ActivateAisleUseCase = Depends(get_activate_aisle_use_case),
) -> AisleResponse:
    """Re-activate a soft-deactivated aisle."""
    try:
        aisle = use_case.execute(
            ActivateAisleCommand(inventory_id=inventory_id, aisle_id=aisle_id)
        )
        return aisle_to_response(aisle)
    except AisleNotFoundError as e:
        reraise_if_mapped(e)
        raise


@router.get("/{inventory_id}/aisles", response_model=PaginatedAisleListResponse)
def list_aisles(
    inventory_id: str,
    use_case: ListAislesWithStatusUseCase = Depends(get_list_aisles_with_status_use_case),
    search: str | None = Query(None, description="Case-insensitive substring on aisle code."),
    status: str | None = Query(None, description="Exact aisle status (wire value)."),
    is_active: bool | None = Query(
        None, description="Filter by soft-active flag; omit to return all."
    ),
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
            is_active=is_active,
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
    current_user: AuthUser = Depends(require_observability_capability(CAP_VIEW_TECHNICAL_LOGS)),
    list_jobs_uc: ListAisleJobsUseCase = Depends(get_list_aisle_jobs_use_case),
    artifact_storage=Depends(get_artifact_storage),
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
) -> AisleExecutionLogResponse:
    """Merge execution logs from all jobs listed for this aisle (up to limit); per-job read failures are non-fatal."""
    try:
        assert_inventory_client_scope(
            inventory_repo,
            inventory_id=inventory_id,
            access=ObservabilityAccessContext.from_user(current_user),
        )
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail=HTTP_DETAIL_JOB_NOT_FOUND) from None
    body = _build_aisle_aggregated_execution_log_body(
        inventory_id=inventory_id,
        aisle_id=aisle_id,
        list_jobs_uc=list_jobs_uc,
        artifact_storage=artifact_storage,
    )
    events = body.get("events") or []
    body["events"] = sanitize_execution_log_events(
        events if isinstance(events, list) else [], user=current_user
    )
    return AisleExecutionLogResponse.model_validate(body)


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/execution-log.txt",
    response_class=Response,
)
def get_aisle_aggregated_execution_log_txt(
    inventory_id: str,
    aisle_id: str,
    current_user: AuthUser = Depends(require_observability_capability(CAP_VIEW_TECHNICAL_LOGS)),
    list_jobs_uc: ListAisleJobsUseCase = Depends(get_list_aisle_jobs_use_case),
    artifact_storage=Depends(get_artifact_storage),
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
) -> Response:
    """Plain-text merged execution log for all aisle jobs (UTF-8 download)."""
    try:
        assert_inventory_client_scope(
            inventory_repo,
            inventory_id=inventory_id,
            access=ObservabilityAccessContext.from_user(current_user),
        )
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail=HTTP_DETAIL_JOB_NOT_FOUND) from None
    body = _build_aisle_aggregated_execution_log_body(
        inventory_id=inventory_id,
        aisle_id=aisle_id,
        list_jobs_uc=list_jobs_uc,
        artifact_storage=artifact_storage,
    )
    events = sanitize_execution_log_events(body.get("events") or [], user=current_user)
    text = format_execution_log_plaintext(events)
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
    current_user: AuthUser = Depends(require_observability_capability(CAP_CANCEL_RETRY)),
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    use_case: CancelAisleJobUseCase = Depends(get_cancel_aisle_job_use_case),
) -> JobSummary:
    """Request cancellation of an active v3 process_aisle job.

    Cancellation is cooperative:
    - QUEUED jobs are marked CANCELED immediately (never started).
    - RUNNING jobs are marked CANCEL_REQUESTED; the executor will observe this and
      transition to CANCELED at the next safe checkpoint.
    """
    try:
        assert_inventory_client_scope(
            inventory_repo,
            inventory_id=inventory_id,
            access=ObservabilityAccessContext.from_user(current_user),
        )
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail=HTTP_DETAIL_JOB_NOT_IN_AISLE_INVENTORY) from None
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
    current_user: AuthUser = Depends(require_observability_capability(CAP_CANCEL_RETRY)),
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    use_case: RetryAisleJobUseCase = Depends(get_retry_aisle_job_use_case),
) -> JobSummary:
    try:
        assert_inventory_client_scope(
            inventory_repo,
            inventory_id=inventory_id,
            access=ObservabilityAccessContext.from_user(current_user),
        )
    except InventoryNotFoundError:
        raise HTTPException(status_code=404, detail=HTTP_DETAIL_JOB_NOT_IN_AISLE_INVENTORY) from None
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
    current_user: AuthUser = Depends(require_observability_capability(CAP_VIEW_SUMMARY)),
    resolve_uc: ResolveAisleJobForInventoryReadUseCase = Depends(
        get_resolve_aisle_job_for_inventory_read_use_case
    ),
    stale_reconciler: JobStaleReconciler = Depends(get_job_stale_reconciler),
    assessment_service: FinalizationAssessmentService = Depends(get_finalization_assessment_service),
    artifact_publication_outbox=Depends(get_artifact_publication_outbox_store),
) -> JobDetailResponse:
    job = _load_job_for_inventory_job_route(resolve_uc, inventory_id, aisle_id, job_id, access_user=current_user)
    reconciled = stale_reconciler.reconcile(job)
    if reconciled is None:
        raise HTTPException(status_code=404, detail=HTTP_DETAIL_JOB_NOT_FOUND)
    assessment = assessment_service.assess(reconciled.id)
    detail = job_to_detail(
        reconciled,
        finalization_assessment=assessment,
        artifact_publication_outbox=artifact_publication_outbox,
    )
    # Sanitize user-visible technical fields on the job detail contract.
    if detail.failure_message:
        detail = detail.model_copy(
            update={
                "failure_message": str(
                    sanitize_observability_value(detail.failure_message, user=current_user)
                )
            }
        )
    if detail.finalization_error_metadata:
        detail = detail.model_copy(
            update={
                "finalization_error_metadata": sanitize_observability_value(
                    detail.finalization_error_metadata, user=current_user
                )
            }
        )
    return detail


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/traceability",
    response_model=JobTraceabilityResponse,
)
def get_job_traceability(
    inventory_id: str,
    aisle_id: str,
    job_id: str,
    current_user: AuthUser = Depends(require_observability_capability(CAP_VIEW_SUMMARY)),
    resolve_uc: ResolveAisleJobForInventoryReadUseCase = Depends(
        get_resolve_aisle_job_for_inventory_read_use_case
    ),
    evidence_query: ResultEvidenceQueryService = Depends(get_result_evidence_query_service),
) -> JobTraceabilityResponse:
    """Structural result_evidence read model and durable traceability artifact metadata."""
    _load_job_for_inventory_job_route(resolve_uc, inventory_id, aisle_id, job_id, access_user=current_user)
    model = evidence_query.get_job_traceability(
        inventory_id=inventory_id,
        aisle_id=aisle_id,
        job_id=job_id,
    )
    resp = job_traceability_to_response(model)
    sanitized = sanitize_observability_value(resp.model_dump(mode="json"), user=current_user)
    return JobTraceabilityResponse.model_validate(sanitized)


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/execution-log",
    response_model=ExecutionLogResponse,
)
def get_job_execution_log(
    inventory_id: str,
    aisle_id: str,
    job_id: str,
    current_user: AuthUser = Depends(require_observability_capability(CAP_VIEW_TECHNICAL_LOGS)),
    resolve_uc: ResolveAisleJobForInventoryReadUseCase = Depends(
        get_resolve_aisle_job_for_inventory_read_use_case
    ),
    artifact_storage=Depends(get_artifact_storage),
) -> ExecutionLogResponse:
    """Structured execution log for this job row; JSONL may cite other ``payload.job_id`` values (envelope + derived fields)."""
    job = _load_job_for_inventory_job_route(resolve_uc, inventory_id, aisle_id, job_id, access_user=current_user)
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
    payload["events"] = sanitize_execution_log_events(
        payload.get("events") or [], user=current_user
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
    current_user: AuthUser = Depends(require_observability_capability(CAP_VIEW_TECHNICAL_LOGS)),
    resolve_uc: ResolveAisleJobForInventoryReadUseCase = Depends(
        get_resolve_aisle_job_for_inventory_read_use_case
    ),
    artifact_storage=Depends(get_artifact_storage),
) -> Response:
    """Plain-text execution log for download (same artifact as JSON execution-log)."""
    job = _load_job_for_inventory_job_route(resolve_uc, inventory_id, aisle_id, job_id, access_user=current_user)
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
    events = sanitize_execution_log_events(body.get("events") or [], user=current_user)
    text = format_execution_log_plaintext(events)
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
    current_user: AuthUser = Depends(require_observability_capability(CAP_VIEW_SUMMARY)),
    resolve_uc: ResolveAisleJobForInventoryReadUseCase = Depends(
        get_resolve_aisle_job_for_inventory_read_use_case
    ),
    artifact_storage=Depends(get_artifact_storage),
) -> dict[str, Any]:
    """Return pipeline hybrid_report.json (dict) from durable artifact metadata or legacy disk."""
    job = _load_job_for_inventory_job_route(resolve_uc, inventory_id, aisle_id, job_id, access_user=current_user)
    try:
        raw = load_hybrid_report_json_for_api(job, artifact_store=artifact_storage)
        sanitized = sanitize_observability_value(raw, user=current_user)
        if not isinstance(sanitized, dict):
            raise HTTPException(status_code=500, detail="Hybrid report sanitization failed")
        return sanitized
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
    current_user: AuthUser = Depends(require_observability_capability(CAP_VIEW_TECHNICAL_LOGS)),
    resolve_uc: ResolveAisleJobForInventoryReadUseCase = Depends(
        get_resolve_aisle_job_for_inventory_read_use_case
    ),
    audit_svc: RunAuditabilityService = Depends(get_run_auditability_service),
) -> dict[str, Any]:
    """Aggregated run observability (Phase H): job row, joins, ``result_json``, hybrid_report, execution_log."""
    _load_job_for_inventory_job_route(resolve_uc, inventory_id, aisle_id, job_id, access_user=current_user)
    view = audit_svc.build(job_id)
    if view is None:
        raise HTTPException(status_code=404, detail=HTTP_DETAIL_JOB_NOT_FOUND)
    sanitized = sanitize_observability_value(view.to_jsonable(), user=current_user)
    if not isinstance(sanitized, dict):
        raise HTTPException(status_code=500, detail="Auditability sanitization failed")
    return sanitized


def _artifact_to_response(view: JobArtifactView) -> JobArtifactResponse:
    return JobArtifactResponse(
        id=view.id,
        job_id=view.job_id,
        category=view.category.value,
        kind=view.kind,
        stage=view.stage,
        display_name=view.display_name,
        original_filename=view.original_filename,
        mime_type=view.mime_type,
        size_bytes=view.size_bytes,
        checksum=view.checksum,
        width=view.width,
        height=view.height,
        status=view.status.value,
        is_current=view.is_current,
        is_previewable=view.is_previewable,
        is_downloadable=view.is_downloadable,
        created_at=view.created_at,
        published_at=view.published_at,
        expires_at=view.expires_at,
        source=JobArtifactSourceResponse(
            type=view.source_type,
            source_asset_id=view.source_asset_id,
        ),
    )


def _safe_download_filename(name: str | None, *, fallback: str) -> str:
    raw = (name or fallback).strip() or fallback
    cleaned = "".join(c for c in raw if c.isalnum() or c in ("-", "_", ".", " "))
    cleaned = cleaned.replace('"', "").replace("\n", "").replace("\r", "")[:180]
    return cleaned or fallback


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/artifacts",
    response_model=JobArtifactPageResponse,
)
def list_job_artifacts(
    inventory_id: str,
    aisle_id: str,
    job_id: str,
    current_user: AuthUser = Depends(require_observability_capability(CAP_VIEW_SUMMARY)),
    category: str | None = Query(None),
    kind: str | None = Query(None),
    status: str | None = Query(None),
    is_current: bool | None = Query(None),
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    resolve_uc: ResolveAisleJobForInventoryReadUseCase = Depends(
        get_resolve_aisle_job_for_inventory_read_use_case
    ),
    catalog: JobArtifactCatalogService = Depends(get_job_artifact_catalog_service),
) -> JobArtifactPageResponse:
    job = _load_job_for_inventory_job_route(
        resolve_uc, inventory_id, aisle_id, job_id, access_user=current_user
    )
    try:
        page = catalog.list_for_job(
            job,
            aisle_id=aisle_id,
            category=category,
            kind=kind,
            status=status,
            cursor=cursor,
            limit=limit,
            is_current=is_current,
        )
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="INVALID_CURSOR") from exc
    return JobArtifactPageResponse(
        items=[_artifact_to_response(i) for i in page.items],
        page=CursorPageMeta(next_cursor=page.next_cursor, has_more=page.has_more),
        inputs_legacy_unverified=page.inputs_legacy_unverified,
        input_snapshot_failed=bool((job.result_json or {}).get("input_snapshot_failed")),
    )


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/artifacts/{artifact_id}",
    response_model=JobArtifactResponse,
)
def get_job_artifact_metadata(
    inventory_id: str,
    aisle_id: str,
    job_id: str,
    artifact_id: str,
    current_user: AuthUser = Depends(require_observability_capability(CAP_VIEW_SUMMARY)),
    resolve_uc: ResolveAisleJobForInventoryReadUseCase = Depends(
        get_resolve_aisle_job_for_inventory_read_use_case
    ),
    catalog: JobArtifactCatalogService = Depends(get_job_artifact_catalog_service),
) -> JobArtifactResponse:
    job = _load_job_for_inventory_job_route(
        resolve_uc, inventory_id, aisle_id, job_id, access_user=current_user
    )
    view = catalog.get_for_job(job, aisle_id=aisle_id, artifact_id=artifact_id)
    if view is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return _artifact_to_response(view)


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/artifacts/{artifact_id}/download",
)
def download_job_artifact(
    inventory_id: str,
    aisle_id: str,
    job_id: str,
    artifact_id: str,
    current_user: AuthUser = Depends(require_observability_capability(CAP_DOWNLOAD_ARTIFACTS)),
    resolve_uc: ResolveAisleJobForInventoryReadUseCase = Depends(
        get_resolve_aisle_job_for_inventory_read_use_case
    ),
    catalog: JobArtifactCatalogService = Depends(get_job_artifact_catalog_service),
    artifact_storage=Depends(get_artifact_storage),
) -> Response:
    job = _load_job_for_inventory_job_route(
        resolve_uc, inventory_id, aisle_id, job_id, access_user=current_user
    )
    view = catalog.get_for_job(job, aisle_id=aisle_id, artifact_id=artifact_id)
    if view is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    if not view.is_downloadable or view.status.value != "AVAILABLE":
        raise HTTPException(
            status_code=409,
            detail=f"Artifact is not downloadable (status={view.status.value})",
        )
    key = (view.storage_key or "").strip()
    if not key:
        raise HTTPException(status_code=404, detail="Artifact storage key missing")
    if view.source_type == "generated":
        try:
            assert_job_owned_storage_key(job_id=job.id, storage_key=key)
        except ValueError:
            logger.warning(
                "artifact_storage_key_namespace_violation job_id=%s artifact_id=%s",
                job.id,
                artifact_id,
            )
            raise HTTPException(status_code=404, detail="Artifact not found") from None
    settings = load_settings()
    # Always proxy through the API. A 307 to a GCS/S3 signed URL breaks browser
    # ``fetch`` downloads (CORS). Authenticated same-origin streaming works with
    # ``apiDownloadBlob``.
    import os
    import tempfile
    from pathlib import Path

    from fastapi.responses import StreamingResponse

    max_bytes = int(getattr(settings, "observability_download_max_bytes", 0) or 0)
    max_concurrent = int(getattr(settings, "observability_download_max_concurrent", 4) or 4)
    # Hold the slot for the full stream lifetime (released in _iter_chunks finally).
    slot_cm = acquire_download_slot(max_concurrent=max_concurrent)
    slot_cm.__enter__()
    try:
        try:
            meta = artifact_storage.get_object_metadata(key)
            declared_size = int(getattr(meta, "file_size_bytes", 0) or 0)
            if max_bytes > 0 and declared_size > max_bytes:
                raise HTTPException(status_code=413, detail="Artifact exceeds download size limit")
        except HTTPException:
            raise
        except Exception:
            logger.debug("artifact_head_unavailable job_id=%s artifact_id=%s", job.id, artifact_id)

        temp_dir = getattr(settings, "observability_download_temp_dir", None) or None
        if temp_dir:
            Path(str(temp_dir)).mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix="artifact_dl_",
            suffix=".bin",
            dir=str(temp_dir) if temp_dir else None,
        )
        os.close(fd)
        tmp_path = Path(tmp_name)
        try:
            artifact_storage.download_to_path(key, tmp_path)
        except Exception as exc:
            tmp_path.unlink(missing_ok=True)
            logger.warning(
                "artifact_download_failed job_id=%s artifact_id=%s err=%s", job.id, artifact_id, exc
            )
            raise HTTPException(status_code=404, detail="Artifact content not available") from None
        size = tmp_path.stat().st_size
        if max_bytes > 0 and size > max_bytes:
            tmp_path.unlink(missing_ok=True)
            raise HTTPException(status_code=413, detail="Artifact exceeds download size limit")
        filename = _safe_download_filename(
            resolve_artifact_download_filename(
                kind=view.kind,
                original_filename=view.original_filename,
                mime_type=view.mime_type,
                storage_key=view.storage_key,
            ),
            fallback=resolve_artifact_download_filename(kind=view.kind, mime_type=view.mime_type),
        )

        def _iter_chunks():
            sent = 0
            try:
                with open(tmp_path, "rb") as fh:
                    while True:
                        chunk = fh.read(64 * 1024)
                        if not chunk:
                            break
                        sent += len(chunk)
                        if max_bytes > 0 and sent > max_bytes:
                            break
                        yield chunk
            finally:
                tmp_path.unlink(missing_ok=True)
                slot_cm.__exit__(None, None, None)

        return StreamingResponse(
            _iter_chunks(),
            media_type=view.mime_type or "application/octet-stream",
            headers={
                "Content-Disposition": content_disposition_attachment(filename),
                "Cache-Control": "no-store",
                "Content-Length": str(size),
            },
        )
    except Exception:
        slot_cm.__exit__(None, None, None)
        raise


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/artifacts/{artifact_id}/preview",
    response_model=ArtifactPreviewResponse,
)
def preview_job_artifact(
    inventory_id: str,
    aisle_id: str,
    job_id: str,
    artifact_id: str,
    current_user: AuthUser = Depends(require_observability_capability(CAP_VIEW_ARTIFACT_PREVIEW)),
    resolve_uc: ResolveAisleJobForInventoryReadUseCase = Depends(
        get_resolve_aisle_job_for_inventory_read_use_case
    ),
    catalog: JobArtifactCatalogService = Depends(get_job_artifact_catalog_service),
    artifact_storage=Depends(get_artifact_storage),
) -> ArtifactPreviewResponse:
    job = _load_job_for_inventory_job_route(
        resolve_uc, inventory_id, aisle_id, job_id, access_user=current_user
    )
    view = catalog.get_for_job(job, aisle_id=aisle_id, artifact_id=artifact_id)
    if view is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    if view.status.value != "AVAILABLE" or not view.is_previewable:
        return ArtifactPreviewResponse(
            artifact_id=view.id,
            kind=view.kind,
            mime_type=view.mime_type,
            truncated=False,
            preview_kind="metadata",
            content=None,
            size_bytes=view.size_bytes,
            status=view.status.value,
        )
    key = (view.storage_key or "").strip()
    if not key:
        raise HTTPException(status_code=404, detail="Artifact storage key missing")
    if view.source_type == "generated":
        try:
            assert_job_owned_storage_key(job_id=job.id, storage_key=key)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Artifact not found") from exc
    settings = load_settings()
    mime = (view.mime_type or "").lower()
    max_bytes = settings.observability_text_preview_max_bytes
    preview_kind: str = "text"
    if "json" in mime or mime.endswith("+json"):
        max_bytes = settings.observability_json_preview_max_bytes
        preview_kind = "json"
    elif mime.startswith("image/"):
        return ArtifactPreviewResponse(
            artifact_id=view.id,
            kind=view.kind,
            mime_type=view.mime_type,
            truncated=False,
            preview_kind="metadata",
            content=None,
            size_bytes=view.size_bytes,
            status=view.status.value,
        )
    try:
        raw = artifact_storage.read_range(key, start=0, length=int(max_bytes) + 1)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Artifact content not available") from exc
    truncated = len(raw) > max_bytes
    chunk = raw[:max_bytes]
    try:
        text = chunk.decode("utf-8")
    except UnicodeDecodeError:
        text = chunk.decode("utf-8", errors="replace")
    text = redact_secrets_in_text(text)
    text = str(sanitize_observability_value(text, user=current_user))
    valid_json: bool | None = None
    partial: bool | None = None
    if preview_kind == "json":
        import json as _json

        try:
            _json.loads(text)
            valid_json = True
            partial = False
        except Exception:
            valid_json = False
            partial = True
    return ArtifactPreviewResponse(
        artifact_id=view.id,
        kind=view.kind,
        mime_type=view.mime_type,
        truncated=truncated,
        preview_kind=preview_kind,  # type: ignore[arg-type]
        content=text,
        size_bytes=view.size_bytes,
        status=view.status.value,
        valid_json=valid_json,
        partial=partial,
    )


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/retry-chain",
    response_model=JobRetryChainResponse,
)
def get_job_retry_chain(
    inventory_id: str,
    aisle_id: str,
    job_id: str,
    current_user: AuthUser = Depends(require_observability_capability(CAP_VIEW_SUMMARY)),
    resolve_uc: ResolveAisleJobForInventoryReadUseCase = Depends(
        get_resolve_aisle_job_for_inventory_read_use_case
    ),
    chain_svc: JobRetryChainService = Depends(get_job_retry_chain_service),
) -> JobRetryChainResponse:
    job = _load_job_for_inventory_job_route(
        resolve_uc, inventory_id, aisle_id, job_id, access_user=current_user
    )
    view = chain_svc.build(job, aisle_id=aisle_id)
    return JobRetryChainResponse(
        root_job_id=view.root_job_id,
        selected_job_id=view.selected_job_id,
        current_job_id=view.current_job_id,
        integrity=view.integrity.value,
        warnings=list(view.warnings),
        attempts=[
            RetryChainAttemptResponse(
                job_id=a.job_id,
                attempt_number=a.attempt_number,
                status=a.status,
                started_at=a.started_at,
                finished_at=a.finished_at,
                failure_code=a.failure_code,
                failure_message=str(
                    sanitize_observability_value(a.failure_message, user=current_user) or ""
                )
                or None,
                execution_id=a.execution_id,
                provider_name=a.provider_name,
                model_name=a.model_name,
                is_selected=a.is_selected,
                is_current=a.is_current,
                is_successful=a.is_successful,
            )
            for a in view.attempts
        ],
        edges=[
            RetryChainEdgeResponse(from_job_id=e.from_job_id, to_job_id=e.to_job_id)
            for e in view.edges
        ],
    )


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/execution-log/page",
    response_model=ExecutionLogPageResponse,
)
def get_job_execution_log_page(
    inventory_id: str,
    aisle_id: str,
    job_id: str,
    current_user: AuthUser = Depends(require_observability_capability(CAP_VIEW_TECHNICAL_LOGS)),
    cursor: str | None = Query(None),
    limit: int | None = Query(None, ge=1, le=1000),
    level: str | None = Query(None),
    stage: str | None = Query(None),
    search: str | None = Query(None),
    sort_order: str = Query("asc"),
    resolve_uc: ResolveAisleJobForInventoryReadUseCase = Depends(
        get_resolve_aisle_job_for_inventory_read_use_case
    ),
    artifact_storage=Depends(get_artifact_storage),
) -> ExecutionLogPageResponse:
    """Paginated execution-log events via ranged JSONL reads when storage supports it."""
    job = _load_job_for_inventory_job_route(
        resolve_uc, inventory_id, aisle_id, job_id, access_user=current_user
    )
    settings = load_settings()
    page_size = limit if limit is not None else settings.observability_log_page_size
    max_scan = int(getattr(settings, "observability_log_max_scan_bytes", 8_000_000) or 8_000_000)
    page = None
    remote = resolve_execution_log_meta(job)
    if remote is not None and (sort_order or "asc").strip().lower() != "desc":
        key, bucket, _meta = remote
        try:
            page, _identity = paginate_execution_log_ranged(
                artifact_store=artifact_storage,
                storage_key=key,
                bucket=bucket,
                cursor=cursor,
                limit=int(page_size),
                max_limit=settings.observability_log_max_page_size,
                max_scan_bytes=max_scan,
                level=level,
                stage=stage,
                search=search,
                sort_order=sort_order,
            )
        except InvalidCursorError as exc:
            raise HTTPException(status_code=400, detail="INVALID_CURSOR") from exc
        except LogChangedError as exc:
            raise HTTPException(status_code=409, detail="LOG_CHANGED") from exc
        except Exception:
            logger.debug("ranged_log_page_fallback job_id=%s", job.id, exc_info=True)
            page = None

    if page is None:
        tmp_path = None
        is_temp = False
        try:
            tmp_path, is_temp = open_execution_log_tempfile(job, artifact_store=artifact_storage)
            with open(tmp_path, "rb") as stream:
                try:
                    page = paginate_jsonl_stream(
                        stream,
                        cursor=cursor,
                        limit=int(page_size),
                        max_limit=settings.observability_log_max_page_size,
                        max_scan_bytes=max_scan,
                        level=level,
                        stage=stage,
                        search=search,
                        sort_order=sort_order,
                    )
                    if remote is not None:
                        # Remote path fell back to full temp download — do not claim scalable mode.
                        page = type(page)(
                            items=page.items,
                            next_cursor=page.next_cursor,
                            has_more=page.has_more,
                            mode="legacy_capped",
                            truncated=page.truncated,
                            bytes_scanned=page.bytes_scanned,
                            available_levels=page.available_levels,
                            available_stages=page.available_stages,
                        )
                except InvalidCursorError as exc:
                    raise HTTPException(
                        status_code=400,
                        detail="INVALID_CURSOR",
                    ) from exc
        except StoredArtifactAccessError as e:
            reraise_if_mapped(e, cause=e)
            raise
        finally:
            if is_temp and tmp_path is not None:
                tmp_path.unlink(missing_ok=True)

    items = sanitize_execution_log_events(page.items, user=current_user)
    return ExecutionLogPageResponse(
        inventory_id=inventory_id,
        aisle_id=aisle_id,
        requested_job_id=job_id,
        items=items,
        page=CursorPageMeta(next_cursor=page.next_cursor, has_more=page.has_more),
        filters=ExecutionLogFiltersMeta(
            available_levels=page.available_levels,
            available_stages=page.available_stages,
            available_event_types=[],
        ),
        pagination_mode=page.mode,
        truncated=page.truncated,
        bytes_scanned=page.bytes_scanned,
    )


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/timeline",
    response_model=JobTimelinePageResponse,
)
def get_job_timeline(
    inventory_id: str,
    aisle_id: str,
    job_id: str,
    current_user: AuthUser = Depends(require_observability_capability(CAP_VIEW_SUMMARY)),
    cursor: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    stage: str | None = Query(None),
    event_type: str | None = Query(None),
    level: str | None = Query(None),
    resolve_uc: ResolveAisleJobForInventoryReadUseCase = Depends(
        get_resolve_aisle_job_for_inventory_read_use_case
    ),
    artifact_storage=Depends(get_artifact_storage),
) -> JobTimelinePageResponse:
    job = _load_job_for_inventory_job_route(
        resolve_uc, inventory_id, aisle_id, job_id, access_user=current_user
    )
    settings = load_settings()
    max_scan = int(getattr(settings, "observability_log_max_scan_bytes", 8_000_000) or 8_000_000)
    page_mode = "incremental"
    truncated = False
    bytes_scanned = 0
    raw_events: list[dict[str, Any]] = []
    next_cursor: str | None = None
    has_more = False

    remote = resolve_execution_log_meta(job)
    try:
        if remote is not None:
            key, bucket, _meta = remote
            log_page, _identity = paginate_execution_log_ranged(
                artifact_store=artifact_storage,
                storage_key=key,
                bucket=bucket,
                cursor=cursor,
                limit=limit,
                max_limit=500,
                max_scan_bytes=max_scan,
                level=level,
                stage=stage,
                search=None,
                sort_order="asc",
            )
            raw_events = log_page.items
            next_cursor = log_page.next_cursor
            has_more = log_page.has_more
            truncated = log_page.truncated
            bytes_scanned = log_page.bytes_scanned
            page_mode = log_page.mode
        else:
            tmp_path, is_temp = open_execution_log_tempfile(job, artifact_store=artifact_storage)
            try:
                with open(tmp_path, "rb") as stream:
                    log_page = paginate_jsonl_stream(
                        stream,
                        cursor=cursor,
                        limit=limit,
                        max_limit=500,
                        max_scan_bytes=max_scan,
                        level=level,
                        stage=stage,
                        sort_order="asc",
                    )
                raw_events = log_page.items
                next_cursor = log_page.next_cursor
                has_more = log_page.has_more
                truncated = log_page.truncated
                bytes_scanned = log_page.bytes_scanned
                page_mode = log_page.mode
            finally:
                if is_temp:
                    tmp_path.unlink(missing_ok=True)
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="INVALID_CURSOR") from exc
    except LogChangedError as exc:
        raise HTTPException(status_code=409, detail="LOG_CHANGED") from exc
    except StoredArtifactAccessError as e:
        if getattr(e, "status_code", 404) == 404:
            raw_events = []
        else:
            reraise_if_mapped(e, cause=e)
            raise

    events = derive_timeline_events(
        job_id=job.id,
        execution_id=job.execution_id,
        raw_events=raw_events,
    )
    if event_type:
        et = event_type.strip().upper()
        events = [e for e in events if e.event_type == et]
    return JobTimelinePageResponse(
        items=[
            JobTimelineEventResponse(
                id=e.id,
                job_id=e.job_id,
                execution_id=e.execution_id,
                event_type=e.event_type,
                stage=e.stage,
                level=e.level,
                timestamp=e.timestamp,
                sequence=e.sequence,
                previous_status=e.previous_status,
                new_status=e.new_status,
                message=str(sanitize_observability_value(e.message, user=current_user) or "")
                or None,
                duration_ms=e.duration_ms,
                provider=e.provider,
                provider_request_id=e.provider_request_id,
                error_code=e.error_code,
                metadata=sanitize_observability_value(e.metadata or {}, user=current_user),
            )
            for e in events
        ],
        page=CursorPageMeta(next_cursor=next_cursor, has_more=has_more),
        pagination_mode=page_mode,
        truncated=truncated,
        bytes_scanned=bytes_scanned,
    )


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/errors",
    response_model=JobErrorPageResponse,
)
def get_job_errors(
    inventory_id: str,
    aisle_id: str,
    job_id: str,
    current_user: AuthUser = Depends(require_observability_capability(CAP_VIEW_SUMMARY)),
    cursor: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    resolve_uc: ResolveAisleJobForInventoryReadUseCase = Depends(
        get_resolve_aisle_job_for_inventory_read_use_case
    ),
    artifact_storage=Depends(get_artifact_storage),
) -> JobErrorPageResponse:
    job = _load_job_for_inventory_job_route(
        resolve_uc, inventory_id, aisle_id, job_id, access_user=current_user
    )
    include_stack = principal_has_capability(current_user, CAP_VIEW_STACK_TRACES)
    settings = load_settings()
    max_scan = int(getattr(settings, "observability_log_max_scan_bytes", 8_000_000) or 8_000_000)
    page_mode = "incremental"
    truncated = False
    bytes_scanned = 0
    raw_events: list[dict[str, Any]] = []
    next_cursor: str | None = None
    has_more = False
    remote = resolve_execution_log_meta(job)
    try:
        if remote is not None:
            key, bucket, _meta = remote
            log_page, _identity = paginate_execution_log_ranged(
                artifact_store=artifact_storage,
                storage_key=key,
                bucket=bucket,
                cursor=cursor,
                limit=limit,
                max_limit=500,
                max_scan_bytes=max_scan,
                level="error,critical",
                sort_order="asc",
            )
            raw_events = log_page.items
            next_cursor = log_page.next_cursor
            has_more = log_page.has_more
            truncated = log_page.truncated
            bytes_scanned = log_page.bytes_scanned
            page_mode = log_page.mode
        else:
            tmp_path, is_temp = open_execution_log_tempfile(job, artifact_store=artifact_storage)
            try:
                with open(tmp_path, "rb") as stream:
                    log_page = paginate_jsonl_stream(
                        stream,
                        cursor=cursor,
                        limit=limit,
                        max_limit=500,
                        max_scan_bytes=max_scan,
                        level="error,critical",
                        sort_order="asc",
                    )
                raw_events = log_page.items
                next_cursor = log_page.next_cursor
                has_more = log_page.has_more
                truncated = log_page.truncated
                bytes_scanned = log_page.bytes_scanned
                page_mode = log_page.mode
            finally:
                if is_temp:
                    tmp_path.unlink(missing_ok=True)
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="INVALID_CURSOR") from exc
    except LogChangedError as exc:
        raise HTTPException(status_code=409, detail="LOG_CHANGED") from exc
    except StoredArtifactAccessError:
        raw_events = []

    # Primary job failure first on the first page only.
    primary_items = []
    if not cursor and (job.failure_code or job.failure_message):
        primary_items = collect_job_errors(job, raw_events=[], include_stack_hint=include_stack)
    log_items = collect_job_errors(
        job, raw_events=raw_events, include_stack_hint=include_stack
    )
    # Drop primary duplicate from log_items (collect always prepends primary).
    log_only = [e for e in log_items if e.error_category != "job_failure"]
    items = primary_items + log_only
    return JobErrorPageResponse(
        items=[
            JobErrorResponse(
                error_id=e.error_id,
                job_id=e.job_id,
                stage=e.stage,
                error_category=e.error_category,
                error_code=e.error_code,
                provider=e.provider,
                provider_code=e.provider_code,
                provider_request_id=e.provider_request_id,
                http_status=e.http_status,
                message=str(sanitize_observability_value(e.message, user=current_user) or "")
                or None,
                sanitized_detail=str(
                    sanitize_observability_value(e.sanitized_detail, user=current_user) or ""
                )
                or None,
                retryable=e.retryable,
                attempt_number=e.attempt_number,
                occurred_at=e.occurred_at,
                stack_trace_available=e.stack_trace_available,
            )
            for e in items
        ],
        page=CursorPageMeta(next_cursor=next_cursor, has_more=has_more),
        pagination_mode=page_mode,
        truncated=truncated,
        bytes_scanned=bytes_scanned,
    )


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
