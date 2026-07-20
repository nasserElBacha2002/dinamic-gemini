"""Phase 7 — per-asset processing observability routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, Query

from src.api.dependencies import (
    get_get_asset_processing_detail_use_case,
    get_invalidate_asset_result_use_case,
    get_list_asset_processing_use_case,
    get_list_processing_events_use_case,
    get_reprocess_asset_use_case,
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
    InventoryNotFoundError,
    JobDoesNotBelongToAisleError,
    JobNotFoundError,
    ProcessingObservabilityDisabledError,
    SourceAssetNotFoundForAisleError,
    StrategyDisabledError,
)
from src.application.use_cases.processing.asset_processing_queries import (
    GetAssetProcessingDetailCommand,
    GetAssetProcessingDetailUseCase,
    ListAssetProcessingCommand,
    ListAssetProcessingUseCase,
)
from src.application.use_cases.processing.reprocess_asset import (
    InvalidateAssetResultCommand,
    InvalidateAssetResultUseCase,
    ReprocessAssetCommand,
    ReprocessAssetUseCase,
)
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser

logger = logging.getLogger(__name__)

router = APIRouter()


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
    except (
        InventoryNotFoundError,
        JobNotFoundError,
        JobDoesNotBelongToAisleError,
        AssetNotInJobSnapshotError,
        AssetProcessingStateConcurrencyError,
        StrategyDisabledError,
        ProcessingObservabilityDisabledError,
    ) as exc:
        reraise_if_mapped(exc)
        raise
    return MutationAssetResponse(**raw)


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
    except (
        InventoryNotFoundError,
        JobNotFoundError,
        JobDoesNotBelongToAisleError,
        SourceAssetNotFoundForAisleError,
        AssetProcessingStateConcurrencyError,
        StrategyDisabledError,
        ProcessingObservabilityDisabledError,
    ) as exc:
        reraise_if_mapped(exc)
        raise
    return MutationAssetResponse(**raw)


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
    use_case: ReprocessAssetUseCase = Depends(get_reprocess_asset_use_case),
    user: AuthUser = Depends(get_current_admin),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> MutationAssetResponse:
    """Queue reprocess that reuses durable external normalized results when present."""
    try:
        raw = use_case.execute(
            ReprocessAssetCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                job_id=job_id,
                asset_id=asset_id,
                reason=payload.reason or "RETRY_PERSISTENCE",
                expected_state_version=payload.expected_state_version,
                strategy="EXTERNAL_PROVIDER",
                manual_policy=payload.manual_policy,
                idempotency_key=idempotency_key,
                actor=getattr(user, "email", None) or getattr(user, "sub", None),
            )
        )
    except (
        InventoryNotFoundError,
        JobNotFoundError,
        JobDoesNotBelongToAisleError,
        AssetNotInJobSnapshotError,
        AssetProcessingStateConcurrencyError,
        StrategyDisabledError,
        ProcessingObservabilityDisabledError,
    ) as exc:
        reraise_if_mapped(exc)
        raise
    return MutationAssetResponse(**raw)


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
                reason=payload.reason or "MANUAL_EXTERNAL_FALLBACK",
                expected_state_version=payload.expected_state_version,
                strategy="EXTERNAL_PROVIDER",
                manual_policy=payload.manual_policy,
                idempotency_key=idempotency_key,
                actor=getattr(user, "email", None) or getattr(user, "sub", None),
            )
        )
    except (
        InventoryNotFoundError,
        JobNotFoundError,
        JobDoesNotBelongToAisleError,
        AssetNotInJobSnapshotError,
        AssetProcessingStateConcurrencyError,
        StrategyDisabledError,
        ProcessingObservabilityDisabledError,
    ) as exc:
        reraise_if_mapped(exc)
        raise
    return MutationAssetResponse(**raw)


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
    """Sanitized event export (JSONL or CSV). No secrets."""
    import csv
    import io
    import json

    from fastapi.responses import PlainTextResponse

    try:
        raw = use_case.execute(
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            job_id=job_id,
            asset_id=asset_id,
            page=1,
            page_size=500,
        )
    except (
        InventoryNotFoundError,
        JobNotFoundError,
        JobDoesNotBelongToAisleError,
        SourceAssetNotFoundForAisleError,
        AssetNotInJobSnapshotError,
    ) as exc:
        reraise_if_mapped(exc)
        raise

    logger.info(
        "processing_ui.logs_exported job_id=%s asset_id=%s format=%s count=%s",
        job_id,
        asset_id,
        format,
        raw.get("total", 0),
    )
    items = list(raw.get("items") or [])
    if format == "csv":
        buf = io.StringIO()
        writer = csv.DictWriter(
            buf,
            fieldnames=[
                "timestamp",
                "event_type",
                "asset_id",
                "level",
                "message",
            ],
        )
        writer.writeheader()
        for item in items:
            writer.writerow(
                {
                    "timestamp": item.get("timestamp"),
                    "event_type": item.get("event_type"),
                    "asset_id": asset_id,
                    "level": item.get("level"),
                    "message": item.get("message"),
                }
            )
        return PlainTextResponse(
            buf.getvalue(),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="processing-events-{asset_id}.csv"'
            },
        )
    lines = [
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
        for item in items
    ]
    return PlainTextResponse(
        "\n".join(lines) + ("\n" if lines else ""),
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": f'attachment; filename="processing-events-{asset_id}.jsonl"'
        },
    )
