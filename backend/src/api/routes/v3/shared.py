"""
v3 shared helpers: response mappers, exception mapping, HEIC/normalized path resolution.
Used by v3 route modules (inventories, aisles, assets, positions, reviews).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn

from fastapi import HTTPException

from src.api.constants.error_wire import (
    HTTP_DETAIL_REVIEW_CORRECTED_QUANTITY_REQUIRED_FOR_UPDATE_QUANTITY,
    HTTP_DETAIL_REVIEW_POSITION_CODE_REQUIRED_FOR_UPDATE_POSITION_CODE,
    HTTP_DETAIL_REVIEW_SKU_REQUIRED_FOR_UPDATE_SKU,
)
from src.api.errors import review_exception_to_http
from src.api.schemas.aisle_schemas import AisleJobSummary, AisleResponse
from src.api.schemas.asset_schemas import SourceAssetResponse
from src.api.schemas.benchmark_schemas import LlmCostSnapshotResponse
from src.api.schemas.inventory_schemas import (
    InventoryListItemResponse,
    InventoryResponse,
    PrimaryExecutionConfigResponse,
)
from src.api.schemas.position_schemas import (
    EvidenceResponse,
    PositionProductBlock,
    PositionQuantityBlock,
    PositionSummaryResponse,
    PositionTechnicalSnapshot,
    PositionTraceabilityBlock,
    ReviewActionRequest,
    ReviewActionResponse,
)
from src.api.schemas.processing_schemas import (
    AisleStatusResponse,
    ArtifactPublicationBlock,
    ArtifactPublicationItemResponse,
    AssetProgressResponse,
    FinalizationAssessmentBlock,
    FinalizationStageAssessmentItem,
    JobDetailResponse,
    JobSummary,
)
from src.api.schemas.reference_usage_schemas import ReferenceUsageSummary
from src.api.services.identification_mode_response import (
    IdentificationModeApiFields,
    aisle_identification_fields,
    inventory_identification_fields,
)
from src.application.errors import (
    AisleNotFoundError,
    InventoryNotFoundError,
    PositionDeletedError,
    PositionNotFoundError,
    ProductNotFoundError,
)
from src.application.mappers.position_canonical_view import (
    PositionCanonicalView,
    build_position_canonical_view,
)
from src.application.ports.artifact_publication_outbox_store import (
    ArtifactPublicationOutboxStore,
    MissingMigrationOrStoreUnavailableError,
)
from src.application.ports.contracts import InventoryListItem
from src.application.services.inventory_primary_execution_config import (
    primary_execution_config_for_inventory,
)
from src.application.services.llm_cost_snapshot_public import llm_cost_snapshot_public_dict
from src.application.services.reference_usage_from_job_result import (
    parse_reference_usage_from_result_json,
)
from src.application.services.result_context_resolver import ResultContextResolver
from src.application.use_cases.aisles.get_aisle_processing_status import AisleProcessingStatusResult
from src.application.use_cases.positions.confirm_position import ConfirmPositionUseCase
from src.application.use_cases.positions.delete_position import DeletePositionUseCase
from src.application.use_cases.positions.mark_position_image_mismatch import (
    MarkPositionImageMismatchUseCase,
)
from src.application.use_cases.positions.mark_position_unknown import MarkPositionUnknownUseCase
from src.application.use_cases.positions.update_position_code import UpdatePositionCodeUseCase
from src.application.use_cases.positions.update_product_quantity import UpdateProductQuantityUseCase
from src.application.use_cases.positions.update_product_sku import UpdateProductSkuUseCase
from src.domain.aisle.entities import Aisle
from src.domain.assets.entities import SourceAsset
from src.domain.client.entities import Client
from src.domain.evidence.entities import Evidence
from src.domain.inventory.entities import Inventory
from src.domain.jobs.entities import Job
from src.domain.jobs.finalization_evidence import FinalizationAssessment
from src.domain.positions.entities import Position
from src.domain.products.entities import ProductRecord
from src.domain.reviews.entities import ReviewAction
from src.infrastructure.pipeline.job_finalization_tracker import (
    sanitize_finalization_error_metadata,
)
from src.infrastructure.pipeline.v3_job_executor import RUN_ID
from src.utils.validation import validate_relative_path

logger = logging.getLogger(__name__)

_MANIFEST_FILENAME = "input_manifest.json"
_NORMALIZED_SUBDIR = "input_photos_normalized"
_HEIC_EXTENSIONS = (".heic", ".heif")


def _parse_reference_usage_summary(result_json: Any) -> ReferenceUsageSummary | None:
    """Map persisted visual_reference_context into the compact API summary shape."""
    fields = parse_reference_usage_from_result_json(result_json)
    if fields is None:
        return None
    return ReferenceUsageSummary(
        resolved=fields.resolved,
        resolved_count=fields.resolved_count,
        provider_consumed=fields.provider_consumed,
        provider_consumed_count=fields.provider_consumed_count,
        reference_ids=fields.reference_ids,
        resolution_error=fields.resolution_error,
    )


def _try_resolve_normalized_asset_for_job(
    output_dir: Path,
    job_id: str,
    asset_id: str,
) -> tuple[Path | None, str | None]:
    """Try to resolve normalized image path for one job (no job_repo/aisle_id needed).

    Returns (path, None) on success, (None, reason) on failure.
    """
    run_dir = output_dir / job_id / RUN_ID
    job_dir = run_dir.parent
    if not run_dir.is_dir():
        return None, "job_run_dir_missing"
    manifest_path = job_dir / _MANIFEST_FILENAME
    if not manifest_path.is_file():
        return None, "manifest_missing"
    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None, "manifest_unreadable"
    photos = manifest.get("photos") or []
    for entry in photos:
        if entry.get("image_id") != asset_id:
            continue
        stored_normalized = entry.get("stored_normalized_filename") or ""
        if not stored_normalized:
            return None, "stored_normalized_filename_missing"
        try:
            safe_filename = validate_relative_path(stored_normalized, "stored_normalized_filename")
        except ValueError:
            return None, "path_validation_failed"
        normalized_base = run_dir / _NORMALIZED_SUBDIR
        candidate = normalized_base / safe_filename
        try:
            candidate_resolved = candidate.resolve()
            base_resolved = normalized_base.resolve()
            candidate_resolved.relative_to(base_resolved)
        except (ValueError, OSError):
            return None, "path_validation_failed"
        if not candidate_resolved.is_file():
            return None, "normalized_file_missing"
        return Path(candidate_resolved), None
    return None, "asset_id_not_in_manifest"


def resolve_normalized_asset_path(
    output_dir: Path,
    *,
    inventory_id: str,
    aisle: Aisle,
    asset_id: str,
    explicit_job_id: str | None,
    resolver: ResultContextResolver,
) -> Path | None:
    """Resolve normalized (browser-safe) JPEG path for HEIC/HEIF using :class:`ResultContextResolver`.

    Uses explicit ``job_id`` query param when provided; otherwise operational job or **legacy** slice.
    Legacy slice (``job_id_for_slice is None``) has no per-run manifest folder — returns ``None``.
    **No** implicit latest-job fallback.
    """
    output_dir = Path(output_dir)
    if aisle.inventory_id != inventory_id:
        logger.debug(
            "HEIC preview: aisle inventory mismatch aisle_id=%s expected_inv=%s got_inv=%s",
            aisle.id,
            aisle.inventory_id,
            inventory_id,
        )
        return None
    ctx = resolver.resolve(aisle=aisle, explicit_job_id=explicit_job_id)
    jid = ctx.job_id_for_slice
    if jid is None or not str(jid).strip():
        logger.debug(
            "HEIC preview: no job folder for resolved slice (legacy or unset operational) asset_id=%s",
            asset_id,
        )
        return None
    job_key = str(jid).strip()
    logger.debug(
        "HEIC preview: resolving asset_id=%s with result_context=%s job_id=%s",
        asset_id,
        ctx.source,
        job_key,
    )
    path, reason = _try_resolve_normalized_asset_for_job(output_dir, job_key, asset_id)
    if path is None:
        logger.debug(
            "HEIC preview: resolution failed (%s) asset_id=%s job_id=%s",
            reason,
            asset_id,
            job_key,
        )
    return path


def _raise_review_http_from_route(
    exc: Exception,
    *,
    inventory_id: str,
    aisle_id: str,
    position_id: str,
    job_id: str | None = None,
) -> NoReturn:
    """Delegate to :func:`review_exception_to_http` with stable routing ids for operations logs."""
    raise review_exception_to_http(
        exc,
        inventory_id=inventory_id,
        aisle_id=aisle_id,
        position_id=position_id,
        job_id=job_id,
    )


def handle_confirm(
    inventory_id: str,
    aisle_id: str,
    position_id: str,
    job_id: str | None,
    confirm_uc: ConfirmPositionUseCase,
) -> None:
    try:
        confirm_uc.execute(inventory_id, aisle_id, position_id, job_id)
    except (
        InventoryNotFoundError,
        AisleNotFoundError,
        PositionNotFoundError,
        ValueError,
        PositionDeletedError,
    ) as e:
        raise _raise_review_http_from_route(
            e,
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            position_id=position_id,
            job_id=job_id,
        )


def handle_update_quantity(
    inventory_id: str,
    aisle_id: str,
    position_id: str,
    body: ReviewActionRequest,
    update_quantity_uc: UpdateProductQuantityUseCase,
) -> None:
    if body.corrected_quantity is None:
        raise HTTPException(
            status_code=422,
            detail=HTTP_DETAIL_REVIEW_CORRECTED_QUANTITY_REQUIRED_FOR_UPDATE_QUANTITY,
        )
    try:
        update_quantity_uc.execute(
            inventory_id,
            aisle_id,
            position_id,
            body.job_id,
            (body.product_id or "").strip(),
            body.corrected_quantity,
        )
    except (
        InventoryNotFoundError,
        AisleNotFoundError,
        PositionNotFoundError,
        ProductNotFoundError,
        ValueError,
        PositionDeletedError,
    ) as e:
        raise _raise_review_http_from_route(
            e,
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            position_id=position_id,
            job_id=body.job_id,
        )


def handle_update_sku(
    inventory_id: str,
    aisle_id: str,
    position_id: str,
    body: ReviewActionRequest,
    update_sku_uc: UpdateProductSkuUseCase,
) -> None:
    sku = (body.sku or "").strip() if body.sku is not None else ""
    if not sku:
        raise HTTPException(status_code=422, detail=HTTP_DETAIL_REVIEW_SKU_REQUIRED_FOR_UPDATE_SKU)
    try:
        update_sku_uc.execute(
            inventory_id,
            aisle_id,
            position_id,
            body.job_id,
            (body.product_id or "").strip(),
            sku,
            body.description,
        )
    except (
        InventoryNotFoundError,
        AisleNotFoundError,
        PositionNotFoundError,
        ProductNotFoundError,
        ValueError,
        PositionDeletedError,
    ) as e:
        raise _raise_review_http_from_route(
            e,
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            position_id=position_id,
            job_id=body.job_id,
        )


def handle_update_position_code(
    inventory_id: str,
    aisle_id: str,
    position_id: str,
    body: ReviewActionRequest,
    update_pos_code_uc: UpdatePositionCodeUseCase,
) -> None:
    pos_code = (body.position_code or "").strip()
    if not pos_code:
        raise HTTPException(
            status_code=422,
            detail=HTTP_DETAIL_REVIEW_POSITION_CODE_REQUIRED_FOR_UPDATE_POSITION_CODE,
        )
    try:
        update_pos_code_uc.execute(
            inventory_id,
            aisle_id,
            position_id,
            body.job_id,
            pos_code,
        )
    except (
        InventoryNotFoundError,
        AisleNotFoundError,
        PositionNotFoundError,
        ValueError,
        PositionDeletedError,
    ) as e:
        raise _raise_review_http_from_route(
            e,
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            position_id=position_id,
            job_id=body.job_id,
        )


def handle_mark_unknown(
    inventory_id: str,
    aisle_id: str,
    position_id: str,
    job_id: str | None,
    mark_unknown_uc: MarkPositionUnknownUseCase,
) -> None:
    try:
        mark_unknown_uc.execute(inventory_id, aisle_id, position_id, job_id)
    except (
        InventoryNotFoundError,
        AisleNotFoundError,
        PositionNotFoundError,
        ValueError,
        PositionDeletedError,
    ) as e:
        raise _raise_review_http_from_route(
            e,
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            position_id=position_id,
            job_id=job_id,
        )


def handle_mark_image_mismatch(
    inventory_id: str,
    aisle_id: str,
    position_id: str,
    job_id: str | None,
    uc: MarkPositionImageMismatchUseCase,
) -> None:
    try:
        uc.execute(inventory_id, aisle_id, position_id, job_id)
    except (
        InventoryNotFoundError,
        AisleNotFoundError,
        PositionNotFoundError,
        ValueError,
        PositionDeletedError,
    ) as e:
        raise _raise_review_http_from_route(
            e,
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            position_id=position_id,
            job_id=job_id,
        )


def handle_delete_position(
    inventory_id: str,
    aisle_id: str,
    position_id: str,
    job_id: str | None,
    delete_uc: DeletePositionUseCase,
) -> None:
    try:
        delete_uc.execute(inventory_id, aisle_id, position_id, job_id)
    except (
        InventoryNotFoundError,
        AisleNotFoundError,
        PositionNotFoundError,
        ValueError,
        PositionDeletedError,
    ) as e:
        raise _raise_review_http_from_route(
            e,
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            position_id=position_id,
            job_id=job_id,
        )


def inventory_to_response(
    inv: Inventory,
    *,
    client: Client | None = None,
    identification: IdentificationModeApiFields | None = None,
) -> InventoryResponse:
    pec = primary_execution_config_for_inventory(inv)
    primary_execution_config = (
        PrimaryExecutionConfigResponse(
            provider_name=pec.provider_name,
            model_name=pec.model_name,
            prompt_key=pec.prompt_key,
            prompt_version=pec.prompt_version,
        )
        if pec is not None
        else None
    )
    id_fields = identification or inventory_identification_fields(inv, client=client)
    return InventoryResponse(
        id=inv.id,
        name=inv.name,
        status=inv.status.value,
        processing_mode=inv.processing_mode.value,
        client_id=inv.client_id,
        primary_execution_config=primary_execution_config,
        created_at=inv.created_at,
        updated_at=inv.updated_at,
        identification_mode=id_fields.identification_mode,
        effective_identification_mode=id_fields.effective_identification_mode,
        identification_mode_source=id_fields.identification_mode_source,
    )


def inventory_list_item_to_response(item: InventoryListItem) -> InventoryListItemResponse:
    inv = item.inventory
    return InventoryListItemResponse(
        id=inv.id,
        name=inv.name,
        status=inv.status.value,
        client_id=inv.client_id,
        created_at=inv.created_at,
        updated_at=inv.updated_at,
        aisles_count=item.aisles_count,
        pending_review_count=item.pending_review_count,
        last_activity_at=item.last_activity_at,
        processing_mode=inv.processing_mode.value,
    )


def aisle_to_response(
    a: Aisle,
    latest_job: Job | None = None,
    *,
    assets_count: int = 0,
    positions_count: int = 0,
    pending_review_positions_count: int = 0,
    last_activity_at: datetime | None = None,
    inventory: Inventory | None = None,
    client: Client | None = None,
    identification: IdentificationModeApiFields | None = None,
) -> AisleResponse:
    latest = None
    if latest_job is not None:
        latest = AisleJobSummary(
            id=latest_job.id,
            status=latest_job.status.value,
            created_at=latest_job.created_at,
            updated_at=latest_job.updated_at,
            error_message=latest_job.error_message,
            reference_usage=_parse_reference_usage_summary(latest_job.result_json),
            started_at=latest_job.started_at,
            finished_at=latest_job.finished_at,
            last_heartbeat_at=latest_job.last_heartbeat_at,
            cancel_requested_at=latest_job.cancel_requested_at,
            current_stage=latest_job.current_stage,
            current_substep=latest_job.current_substep,
            current_step_started_at=latest_job.current_step_started_at,
            attempt_count=latest_job.attempt_count,
            retry_of_job_id=latest_job.retry_of_job_id,
            failure_code=latest_job.failure_code,
            failure_message=latest_job.failure_message,
            execution_id=latest_job.execution_id,
            provider_name=latest_job.provider_name,
            model_name=latest_job.model_name,
            prompt_key=latest_job.prompt_key,
        )
    id_fields = identification or aisle_identification_fields(
        a, inventory=inventory, client=client
    )
    return AisleResponse(
        id=a.id,
        inventory_id=a.inventory_id,
        code=a.code,
        status=a.status.value,
        created_at=a.created_at,
        updated_at=a.updated_at,
        is_active=a.is_active,
        error_code=a.error_code,
        error_message=a.error_message,
        operational_job_id=a.operational_job_id,
        client_supplier_id=a.client_supplier_id,
        latest_job=latest,
        assets_count=assets_count,
        positions_count=positions_count,
        pending_review_positions_count=pending_review_positions_count,
        last_activity_at=last_activity_at,
        identification_mode=id_fields.identification_mode,
        effective_identification_mode=id_fields.effective_identification_mode,
        identification_mode_source=id_fields.identification_mode_source,
    )


def status_response_from_result(
    result: AisleProcessingStatusResult,
    *,
    identification: IdentificationModeApiFields | None = None,
) -> AisleStatusResponse:
    job_summary = None
    if result.latest_job is not None:
        job_summary = job_to_summary(result.latest_job)
    recent = [job_to_summary(j) for j in result.recent_jobs]
    return AisleStatusResponse(
        aisle=aisle_to_response(
            result.aisle,
            result.latest_job,
            identification=identification,
        ),
        latest_job=job_summary,
        operational_job_id=result.aisle.operational_job_id,
        recent_jobs=recent,
    )


def _llm_cost_snapshot_from_job_result(
    result_json: dict[str, Any] | None,
) -> LlmCostSnapshotResponse | None:
    d = llm_cost_snapshot_public_dict(result_json)
    if d is None:
        return None
    try:
        return LlmCostSnapshotResponse.model_validate(d)
    except Exception:
        return None


def _asset_progress_from_job_result(
    result_json: dict[str, Any] | None,
) -> AssetProgressResponse | None:
    if not result_json or not isinstance(result_json, dict):
        return None
    raw = result_json.get("asset_progress")
    if not isinstance(raw, dict):
        return None
    try:
        return AssetProgressResponse.model_validate(raw)
    except Exception:
        return None


def _identification_execution_from_job(j: Job) -> dict | None:
    params = j.engine_params_json if isinstance(j.engine_params_json, dict) else None
    if not params:
        return None
    raw = params.get("identification_execution")
    return raw if isinstance(raw, dict) else None


def _client_id_from_job(j: Job) -> str | None:
    params = j.engine_params_json if isinstance(j.engine_params_json, dict) else None
    if not params:
        return None
    cid = params.get("client_id")
    return str(cid).strip() if isinstance(cid, str) and cid.strip() else None


def job_to_summary(j: Job, *, is_operational: bool = False) -> JobSummary:
    return JobSummary(
        id=j.id,
        status=j.status.value,
        created_at=j.created_at,
        updated_at=j.updated_at,
        error_message=j.error_message,
        reference_usage=_parse_reference_usage_summary(j.result_json),
        started_at=j.started_at,
        finished_at=j.finished_at,
        last_heartbeat_at=j.last_heartbeat_at,
        cancel_requested_at=j.cancel_requested_at,
        current_stage=j.current_stage,
        current_substep=j.current_substep,
        current_step_started_at=j.current_step_started_at,
        attempt_count=j.attempt_count,
        retry_of_job_id=j.retry_of_job_id,
        failure_code=j.failure_code,
        failure_message=j.failure_message,
        execution_id=j.execution_id,
        provider_name=j.provider_name,
        model_name=j.model_name,
        prompt_key=j.prompt_key,
        prompt_version=j.prompt_version,
        identification_mode=j.identification_mode.value,
        identification_mode_source=j.identification_mode_source.value,
        execution_strategy=j.execution_strategy.value,
        configuration_snapshot_version=j.configuration_snapshot_version,
        finalization_status=j.finalization_status.value,
        current_finalization_step=(
            j.current_finalization_step.value if j.current_finalization_step else None
        ),
        last_completed_finalization_step=j.last_completed_finalization_step.value,
        finalization_error_code=j.finalization_error_code,
        is_operational=is_operational,
        llm_cost_snapshot=_llm_cost_snapshot_from_job_result(j.result_json),
        asset_progress=_asset_progress_from_job_result(j.result_json),
        identification_execution=_identification_execution_from_job(j),
        client_id=_client_id_from_job(j),
    )


def finalization_assessment_to_response(
    assessment: FinalizationAssessment,
) -> FinalizationAssessmentBlock:
    stages = {
        key: FinalizationStageAssessmentItem(
            stage=value.stage.value,
            status=value.status.value,
            evidence_level=value.evidence_level.value,
            completed_at=value.completed_at,
            verification_required=value.verification_required,
            last_error_code=value.last_error_code,
        )
        for key, value in assessment.stages.items()
    }
    return FinalizationAssessmentBlock(
        outcome=assessment.outcome.value,
        technical_result_status=assessment.technical_result_status,
        finalization_status=assessment.finalization_status,
        last_confirmed_stage=(
            assessment.last_confirmed_stage.value if assessment.last_confirmed_stage else None
        ),
        next_required_stage=(
            assessment.next_required_stage.value if assessment.next_required_stage else None
        ),
        recovery_candidate=assessment.recovery_candidate,
        blocking_reason=assessment.blocking_reason,
        stages=stages,
    )


def artifact_publication_to_response(
    summary,
) -> ArtifactPublicationBlock | None:
    if summary is None:
        return None
    items = [
        ArtifactPublicationItemResponse(
            artifact_kind=item.artifact_kind,
            required=item.required,
            status=item.status.value,
            attempt_count=item.attempt_count,
            max_attempts=item.max_attempts,
            next_attempt_at=item.next_attempt_at,
            last_error_code=item.last_error_code,
            source_type=item.source_type.value,
        )
        for item in summary.items
    ]
    return ArtifactPublicationBlock(
        required_total=summary.required_total,
        required_published=summary.required_published,
        pending=summary.pending,
        retry_scheduled=summary.retry_scheduled,
        permanently_failed=summary.permanently_failed,
        next_attempt_at=summary.next_attempt_at,
        items=items,
    )


def job_to_detail(
    j: Job,
    *,
    is_operational: bool = False,
    finalization_assessment: FinalizationAssessment | None = None,
    artifact_publication_outbox: ArtifactPublicationOutboxStore | None = None,
) -> JobDetailResponse:
    summary = job_to_summary(j, is_operational=is_operational)
    assessment_block = (
        finalization_assessment_to_response(finalization_assessment)
        if finalization_assessment is not None
        else None
    )
    publication_block = None
    if artifact_publication_outbox is not None:
        try:
            publication_block = artifact_publication_to_response(
                artifact_publication_outbox.summary_for_job(j.id)
            )
        except MissingMigrationOrStoreUnavailableError as exc:
            logging.getLogger(__name__).warning(
                "artifact_publication.summary_unavailable job_id=%s error=%s",
                j.id,
                exc,
            )
            publication_block = None
    return JobDetailResponse(
        **summary.model_dump(),
        finalization_started_at=j.finalization_started_at,
        finalization_completed_at=j.finalization_completed_at,
        domain_persisted_at=j.domain_persisted_at,
        artifacts_published_at=j.artifacts_published_at,
        finalization_error_metadata=sanitize_finalization_error_metadata(
            j.finalization_error_metadata
        ),
        finalization_assessment=assessment_block,
        artifact_publication=publication_block,
    )


def asset_to_response(asset: SourceAsset) -> SourceAssetResponse:
    return SourceAssetResponse(
        id=asset.id,
        aisle_id=asset.aisle_id,
        type=asset.type.value,
        original_filename=asset.original_filename,
        storage_path=asset.storage_path,
        mime_type=asset.mime_type,
        uploaded_at=asset.uploaded_at,
        file_size_bytes=asset.file_size_bytes,
    )


def _position_summary_response_from_view(
    p: Position,
    view: PositionCanonicalView,
    *,
    include_technical_snapshot: bool,
) -> PositionSummaryResponse:
    """Single construction site for ``PositionSummaryResponse`` from the canonical view (Sprint 1–2).

    Nested ``product`` / ``quantity`` blocks read only ``view`` — display label, barcode, and
    ``quantity.final`` are resolved in :func:`build_position_canonical_view`. The legacy
    ``detected_summary_json`` surface is passed through only when an endpoint explicitly opts into
    the deprecated technical snapshot for transitional/internal clients.
    """
    detected_summary_json = (
        p.detected_summary_json
        if include_technical_snapshot and isinstance(p.detected_summary_json, dict)
        else None
    )
    product_block = PositionProductBlock(
        id=view.product.primary_product_id,
        sku=view.product.public_sku,
        display_label=view.product.display_label,
        barcode=view.product.barcode,
        identity_source=view.product.identity_source,
    )
    quantity_block = PositionQuantityBlock(
        detected=view.quantity.detected_quantity,
        corrected=view.quantity.corrected_quantity,
        final=view.quantity.final_display_quantity,
        source=view.quantity.qty_source,
        inference_reason=view.quantity.qty_inference_reason,
        resolved=view.quantity.qty_resolved,
    )
    trace_block = PositionTraceabilityBlock(
        status=view.traceability.traceability_status,
        source_image_id=view.traceability.source_image_id,
        source_image_original_filename=view.traceability.source_image_original_filename,
        source_image_sequence=view.traceability.source_image_sequence,
        primary_evidence_frame_index=view.traceability.primary_evidence_frame_index,
        primary_evidence_id=view.review.primary_evidence_id,
        has_evidence=view.review.has_evidence,
        has_valid_evidence=view.traceability.has_valid_evidence,
        traceability_warning=view.traceability.traceability_warning,
    )
    return PositionSummaryResponse(
        id=p.id,
        aisle_id=p.aisle_id,
        status=view.review.status,
        review_resolution=view.review.review_resolution,
        confidence=p.confidence,
        needs_review=view.review.needs_review,
        primary_evidence_id=view.review.primary_evidence_id,
        created_at=p.created_at,
        updated_at=p.updated_at,
        detected_summary_json=detected_summary_json,
        product=product_block,
        quantity=quantity_block,
        traceability=trace_block,
        sku=view.product.public_sku,
        detected_quantity=view.quantity.detected_quantity,
        corrected_quantity=view.quantity.corrected_quantity,
        qty=view.quantity.qty,
        qtySource=view.quantity.qty_source,
        qtyInferenceReason=view.quantity.qty_inference_reason,
        qtyResolved=view.quantity.qty_resolved,
        source_image_id=view.traceability.source_image_id,
        traceability_status=view.traceability.traceability_status,
        has_evidence=view.review.has_evidence,
        source_image_original_filename=view.traceability.source_image_original_filename,
        position_code=view.position_code,
        job_id=p.job_id,
        creation_source=p.creation_source.value
        if hasattr(p, "creation_source") and p.creation_source is not None
        else "automatic",
    )


def technical_snapshot_from_view(
    view: PositionCanonicalView,
) -> PositionTechnicalSnapshot | None:
    """Extract the detail/debug snapshot from the canonical view without re-reading route inputs."""
    snap = view.technical_snapshot if isinstance(view.technical_snapshot, dict) else None
    if snap is None:
        return None
    aggregated_raw = snap.get("aggregated_from_ids")
    aggregated_from_ids = (
        [str(v).strip() for v in aggregated_raw if isinstance(v, str) and str(v).strip()]
        if isinstance(aggregated_raw, list)
        else None
    )
    audit_raw = snap.get("_audit")
    audit = audit_raw if isinstance(audit_raw, dict) else None
    return PositionTechnicalSnapshot(
        entity_uid=(snap.get("entity_uid") if isinstance(snap.get("entity_uid"), str) else None),
        entity_type=(snap.get("entity_type") if isinstance(snap.get("entity_type"), str) else None),
        internal_code=(
            snap.get("internal_code") if isinstance(snap.get("internal_code"), str) else None
        ),
        review_display_label=(
            snap.get("review_display_label")
            if isinstance(snap.get("review_display_label"), str)
            else None
        ),
        position_barcode=(
            snap.get("position_barcode") if isinstance(snap.get("position_barcode"), str) else None
        ),
        pallet_id=(snap.get("pallet_id") if isinstance(snap.get("pallet_id"), str) else None),
        count_status=(
            snap.get("count_status") if isinstance(snap.get("count_status"), str) else None
        ),
        raw_qty=snap.get("raw_qty"),
        qty_parse_status=(
            snap.get("qty_parse_status") if isinstance(snap.get("qty_parse_status"), str) else None
        ),
        qty_origin_field=(
            snap.get("qty_origin_field") if isinstance(snap.get("qty_origin_field"), str) else None
        ),
        aggregated_from_ids=aggregated_from_ids,
        audit=audit,
    )


def position_to_summary(
    p: Position,
    corrected_quantity: int | None = None,
    primary_product: ProductRecord | None = None,
    *,
    include_technical_snapshot: bool = True,
) -> PositionSummaryResponse:
    """Map domain position (+ optional primary product) to the public summary contract.

    Assembly delegates to :func:`build_position_canonical_view` and
    :func:`_position_summary_response_from_view` (nested ``product`` / ``quantity`` / ``traceability`` — Sprint 2).
    """
    view = build_position_canonical_view(
        p,
        primary_product,
        corrected_quantity=corrected_quantity,
    )
    return _position_summary_response_from_view(
        p,
        view,
        include_technical_snapshot=include_technical_snapshot,
    )


def evidence_to_response(e: Evidence) -> EvidenceResponse:
    return EvidenceResponse(
        id=e.id,
        entity_type=e.entity_type,
        entity_id=e.entity_id,
        type=e.type.value,
        storage_path=e.storage_path,
        source_asset_id=e.source_asset_id,
        is_primary=e.is_primary,
        frame_index=e.frame_index,
        timestamp_ms=e.timestamp_ms,
        bbox_json=e.bbox_json,
        quality_score=e.quality_score,
    )


def review_to_response(r: ReviewAction) -> ReviewActionResponse:
    return ReviewActionResponse(
        id=r.id,
        position_id=r.position_id,
        action_type=r.action_type.value,
        before_json=r.before_json,
        after_json=r.after_json,
        created_at=r.created_at,
        user_id=r.user_id,
        comment=r.comment,
        job_id=r.job_id,
    )


def heic_extensions() -> tuple[str, ...]:
    return _HEIC_EXTENSIONS
