"""Phase 7 — per-asset processing observability routes (corrections)."""

from __future__ import annotations

import csv
import io
import json
import logging

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import StreamingResponse

from src.api.dependencies import (
    get_get_asset_processing_detail_use_case,
    get_invalidate_asset_result_use_case,
    get_list_asset_processing_use_case,
    get_list_processing_events_use_case,
    get_reprocess_asset_use_case,
    get_retry_asset_persistence_use_case,
    get_send_asset_to_external_use_case,
    get_single_asset_command_executor,
)
from src.api.errors.error_mapping import reraise_if_mapped
from src.api.schemas.processing_observability_schemas import (
    AssetProcessingDetailResponse,
    AssetProcessingListResponse,
    AssetProcessingSummaryResponse,
    AvailableAssetActionsResponse,
    InvalidateResultRequest,
    MutationAssetResponse,
    ProcessingEventRecordResponse,
    ProcessingEventsPageResponse,
    ProcessingJobProgressSummaryResponse,
    ReprocessAssetRequest,
)
from src.application.errors import (
    AssetNotInJobSnapshotError,
    AssetProcessingStateConcurrencyError,
    DurableCommandMissingError,
    IdempotencyKeyReusedError,
    InventoryNotFoundError,
    JobDoesNotBelongToAisleError,
    JobNotFoundError,
    ProcessingObservabilityDisabledError,
    SourceAssetNotFoundForAisleError,
    StrategyDisabledError,
)
from src.application.services.image_processing.processing_evidence_sanitizer import (
    csv_safe_cell,
)
from src.application.use_cases.processing.asset_processing_queries import (
    GetAssetProcessingDetailCommand,
    GetAssetProcessingDetailUseCase,
    ListAssetProcessingCommand,
    ListAssetProcessingUseCase,
)
from src.application.use_cases.processing.invalidate_asset_result import (
    InvalidateAssetResultCommand,
    InvalidateAssetResultUseCase,
)
from src.application.use_cases.processing.reprocess_asset import (
    ReprocessAssetCommand,
    ReprocessAssetUseCase,
    RetryAssetPersistenceUseCase,
    RetryPersistenceCommand,
    SendAssetToExternalUseCase,
    SendToExternalCommand,
)
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.config import load_settings

logger = logging.getLogger(__name__)

router = APIRouter()

_MUTATION_ERRORS = (
    InventoryNotFoundError,
    JobNotFoundError,
    JobDoesNotBelongToAisleError,
    AssetNotInJobSnapshotError,
    AssetProcessingStateConcurrencyError,
    StrategyDisabledError,
    ProcessingObservabilityDisabledError,
    IdempotencyKeyReusedError,
    DurableCommandMissingError,
    SourceAssetNotFoundForAisleError,
)


def _require_observability_reads() -> None:
    settings = load_settings()
    if not bool(getattr(settings, "processing_observability_enabled", False)):
        raise ProcessingObservabilityDisabledError("PROCESSING_OBSERVABILITY_ENABLED=false")


def _require_logs_ui() -> None:
    _require_observability_reads()
    settings = load_settings()
    if not bool(getattr(settings, "processing_asset_logs_ui_enabled", False)):
        raise ProcessingObservabilityDisabledError("PROCESSING_ASSET_LOGS_UI_ENABLED=false")


def _kick_executor(command_id: str | None) -> None:
    if not command_id:
        return
    try:
        executor = get_single_asset_command_executor()
        executor.execute_command(command_id)
    except Exception as exc:  # best-effort kick; command remains QUEUED
        logger.warning(
            "single_asset_executor.kick_failed command_id=%s err=%s", command_id, exc
        )


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/processing",
    response_model=AssetProcessingListResponse,
)
def list_asset_processing(
    inventory_id: str,
    aisle_id: str,
    job_id: str,
    status: str | None = Query(None),
    strategy: str | None = Query(None),
    resolved_by: str | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    has_warnings: bool | None = Query(None),
    has_fallback: bool | None = Query(None),
    use_case: ListAssetProcessingUseCase = Depends(get_list_asset_processing_use_case),
    _user: AuthUser = Depends(get_current_admin),
) -> AssetProcessingListResponse:
    try:
        _require_observability_reads()
        raw = use_case.execute(
            ListAssetProcessingCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                job_id=job_id,
                status=status,
                strategy=strategy,
                resolved_by=resolved_by,
                search=search,
                page=page,
                page_size=page_size,
                has_warnings=has_warnings,
                has_fallback=has_fallback,
            )
        )
    except (
        InventoryNotFoundError,
        JobNotFoundError,
        JobDoesNotBelongToAisleError,
        ProcessingObservabilityDisabledError,
    ) as exc:
        reraise_if_mapped(exc)
        raise
    summary = raw.get("summary") or {}
    return AssetProcessingListResponse(
        items=[AssetProcessingSummaryResponse(**item) for item in raw["items"]],
        total=raw["total"],
        page=raw["page"],
        page_size=raw["page_size"],
        summary=ProcessingJobProgressSummaryResponse(**summary) if summary else None,
    )


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/processing-detail",
    response_model=AssetProcessingDetailResponse,
)
def get_asset_processing_detail(
    inventory_id: str,
    aisle_id: str,
    job_id: str,
    asset_id: str,
    use_case: GetAssetProcessingDetailUseCase = Depends(
        get_get_asset_processing_detail_use_case
    ),
    _user: AuthUser = Depends(get_current_admin),
) -> AssetProcessingDetailResponse:
    try:
        _require_observability_reads()
        raw = use_case.execute(
            GetAssetProcessingDetailCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                job_id=job_id,
                asset_id=asset_id,
            )
        )
    except (
        InventoryNotFoundError,
        JobNotFoundError,
        JobDoesNotBelongToAisleError,
        SourceAssetNotFoundForAisleError,
        AssetNotInJobSnapshotError,
        ProcessingObservabilityDisabledError,
    ) as exc:
        reraise_if_mapped(exc)
        raise
    actions = raw["available_actions"]
    return AssetProcessingDetailResponse(
        asset=AssetProcessingSummaryResponse(**raw["asset"]),
        current_state=raw.get("current_state") or {},
        active_result=raw.get("active_result"),
        position=raw.get("position"),
        attempts=list(raw.get("attempts") or []),
        external_requests=list(raw.get("external_requests") or []),
        profile_snapshot=raw.get("profile_snapshot"),
        events=list(raw.get("events") or []),
        available_actions=AvailableAssetActionsResponse(**actions),
        historical_incomplete=bool(raw.get("historical_incomplete")),
    )


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/processing-events",
    response_model=ProcessingEventsPageResponse,
)
def list_processing_events(
    inventory_id: str,
    aisle_id: str,
    job_id: str,
    asset_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    use_case=Depends(get_list_processing_events_use_case),
    _user: AuthUser = Depends(get_current_admin),
) -> ProcessingEventsPageResponse:
    try:
        _require_logs_ui()
        raw = use_case.execute(
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            job_id=job_id,
            asset_id=asset_id,
            page=page,
            page_size=page_size,
        )
    except (
        InventoryNotFoundError,
        JobNotFoundError,
        JobDoesNotBelongToAisleError,
        SourceAssetNotFoundForAisleError,
        AssetNotInJobSnapshotError,
        ProcessingObservabilityDisabledError,
    ) as exc:
        reraise_if_mapped(exc)
        raise
    return ProcessingEventsPageResponse(
        items=[ProcessingEventRecordResponse(**i) for i in raw["items"]],
        total=raw["total"],
        page=raw["page"],
        page_size=raw["page_size"],
        has_more=raw.get("has_more", False),
    )


def _mutation_response(raw: dict) -> MutationAssetResponse:
    return MutationAssetResponse(
        asset_id=raw["asset_id"],
        state_version=int(raw.get("state_version") or 0),
        status=raw.get("status"),
        command_id=raw.get("command_id"),
        command_type=raw.get("command_type"),
        idempotent_replay=bool(raw.get("idempotent_replay", False)),
    )


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/reprocess",
    response_model=MutationAssetResponse,
)
def reprocess_asset(
    inventory_id: str,
    aisle_id: str,
    job_id: str,
    asset_id: str,
    payload: ReprocessAssetRequest,
    use_case: ReprocessAssetUseCase = Depends(get_reprocess_asset_use_case),
    user: AuthUser = Depends(get_current_admin),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> MutationAssetResponse:
    try:
        raw = use_case.execute(
            ReprocessAssetCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                job_id=job_id,
                asset_id=asset_id,
                reason=payload.reason,
                expected_state_version=payload.expected_state_version,
                strategy=payload.strategy,
                manual_policy=payload.manual_policy,
                idempotency_key=idempotency_key,
                actor=getattr(user, "email", None) or getattr(user, "sub", None),
            )
        )
    except _MUTATION_ERRORS as exc:
        reraise_if_mapped(exc)
        raise
    if not raw.get("idempotent_replay"):
        _kick_executor(raw.get("command_id"))
    return _mutation_response(raw)


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/invalidate-result",
    response_model=MutationAssetResponse,
)
def invalidate_asset_result(
    inventory_id: str,
    aisle_id: str,
    job_id: str,
    asset_id: str,
    payload: InvalidateResultRequest,
    use_case: InvalidateAssetResultUseCase = Depends(get_invalidate_asset_result_use_case),
    user: AuthUser = Depends(get_current_admin),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> MutationAssetResponse:
    try:
        raw = use_case.execute(
            InvalidateAssetResultCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                job_id=job_id,
                asset_id=asset_id,
                reason=payload.reason,
                expected_state_version=payload.expected_state_version,
                idempotency_key=idempotency_key,
                actor=getattr(user, "email", None) or getattr(user, "sub", None),
            )
        )
    except _MUTATION_ERRORS as exc:
        reraise_if_mapped(exc)
        raise
    return _mutation_response(raw)


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/retry-persistence",
    response_model=MutationAssetResponse,
)
def retry_asset_persistence(
    inventory_id: str,
    aisle_id: str,
    job_id: str,
    asset_id: str,
    payload: ReprocessAssetRequest,
    use_case: RetryAssetPersistenceUseCase = Depends(get_retry_asset_persistence_use_case),
    user: AuthUser = Depends(get_current_admin),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> MutationAssetResponse:
    try:
        raw = use_case.execute(
            RetryPersistenceCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                job_id=job_id,
                asset_id=asset_id,
                reason=payload.reason or "RETRY_PERSISTENCE",
                expected_state_version=payload.expected_state_version,
                idempotency_key=idempotency_key,
                actor=getattr(user, "email", None) or getattr(user, "sub", None),
            )
        )
    except _MUTATION_ERRORS as exc:
        reraise_if_mapped(exc)
        raise
    if not raw.get("idempotent_replay"):
        _kick_executor(raw.get("command_id"))
    return _mutation_response(raw)


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/send-to-external",
    response_model=MutationAssetResponse,
)
def send_asset_to_external(
    inventory_id: str,
    aisle_id: str,
    job_id: str,
    asset_id: str,
    payload: ReprocessAssetRequest,
    use_case: SendAssetToExternalUseCase = Depends(get_send_asset_to_external_use_case),
    user: AuthUser = Depends(get_current_admin),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> MutationAssetResponse:
    try:
        raw = use_case.execute(
            SendToExternalCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                job_id=job_id,
                asset_id=asset_id,
                reason=payload.reason or "MANUAL_EXTERNAL_FALLBACK",
                expected_state_version=payload.expected_state_version,
                idempotency_key=idempotency_key,
                actor=getattr(user, "email", None) or getattr(user, "sub", None),
            )
        )
    except _MUTATION_ERRORS as exc:
        reraise_if_mapped(exc)
        raise
    if not raw.get("idempotent_replay"):
        _kick_executor(raw.get("command_id"))
    return _mutation_response(raw)


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/processing-events/export",
)
def export_processing_events(
    inventory_id: str,
    aisle_id: str,
    job_id: str,
    asset_id: str,
    format: str = Query("jsonl", alias="format", pattern="^(jsonl|csv)$"),
    use_case=Depends(get_list_processing_events_use_case),
    _user: AuthUser = Depends(get_current_admin),
):
    try:
        _require_logs_ui()
    except ProcessingObservabilityDisabledError as exc:
        reraise_if_mapped(exc)
        raise

    def _iter_pages():
        page = 1
        page_size = 200
        total_emitted = 0
        hard_cap = 10_000
        while True:
            raw = use_case.execute(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                job_id=job_id,
                asset_id=asset_id,
                page=page,
                page_size=page_size,
            )
            items = list(raw.get("items") or [])
            if not items:
                break
            for item in items:
                yield item
                total_emitted += 1
                if total_emitted >= hard_cap:
                    return
            if not raw.get("has_more"):
                break
            page += 1

    logger.info(
        "processing_ui.logs_exported job_id=%s asset_id=%s format=%s",
        job_id,
        asset_id,
        format,
    )

    if format == "csv":

        def csv_stream():
            buf = io.StringIO()
            writer = csv.DictWriter(
                buf,
                fieldnames=["timestamp", "event_type", "asset_id", "level", "message"],
            )
            writer.writeheader()
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)
            for item in _iter_pages():
                writer.writerow(
                    {
                        "timestamp": csv_safe_cell(item.get("timestamp")),
                        "event_type": csv_safe_cell(item.get("event_type")),
                        "asset_id": csv_safe_cell(asset_id),
                        "level": csv_safe_cell(item.get("level")),
                        "message": csv_safe_cell(item.get("message")),
                    }
                )
                yield buf.getvalue()
                buf.seek(0)
                buf.truncate(0)
            yield "# export_limit_note=hard_cap_10000\n"

        return StreamingResponse(
            csv_stream(),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="processing-events-{asset_id}.csv"',
                "X-Export-Hard-Cap": "10000",
            },
        )

    def jsonl_stream():
        for item in _iter_pages():
            yield (
                json.dumps(
                    {
                        "timestamp": item.get("timestamp"),
                        "event_type": item.get("event_type"),
                        "asset_id": asset_id,
                        "level": item.get("level"),
                        "message": item.get("message"),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        yield json.dumps({"export_hard_cap": 10000, "truncated": False}) + "\n"

    return StreamingResponse(
        jsonl_stream(),
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": f'attachment; filename="processing-events-{asset_id}.jsonl"',
            "X-Export-Hard-Cap": "10000",
        },
    )
