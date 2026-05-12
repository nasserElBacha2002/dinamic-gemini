"""v3 observability API — Phase H5 read-only metrics."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.constants.error_wire import (
    HTTP_DETAIL_OBSERVABILITY_METRICS_FROM_MUST_BE_ON_OR_BEFORE_TO,
    HTTP_DETAIL_OBSERVABILITY_METRICS_RANGE_EXCEEDS_MAX_DAYS,
)
from src.api.constants.route_paths import API_V3_OBSERVABILITY_ROUTER_PREFIX
from src.api.dependencies import get_observability_metrics_service
from src.api.schemas.observability_metrics_schemas import ObservabilityMetricsResponse
from src.application.services.observability_metrics_service import (
    ObservabilityMetricsFilters,
    ObservabilityMetricsService,
    resolve_metrics_time_range,
)
from src.auth.dependencies import get_current_admin

router = APIRouter(
    prefix=API_V3_OBSERVABILITY_ROUTER_PREFIX,
    tags=["observability-v3"],
    dependencies=[Depends(get_current_admin)],
)


@router.get("/metrics", response_model=ObservabilityMetricsResponse)
def get_observability_metrics(
    *,
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = Query(None),
    client_id: str | None = Query(None),
    client_supplier_id: str | None = Query(None),
    provider_name: str | None = Query(None),
    model_name: str | None = Query(None),
    svc: ObservabilityMetricsService = Depends(get_observability_metrics_service),
) -> ObservabilityMetricsResponse:
    """Aggregated processing metrics for internal operations (no artifact scans)."""
    try:
        created_from, created_to = resolve_metrics_time_range(from_, to)
    except ValueError as e:
        code = str(e)
        if code == "from_after_to":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=HTTP_DETAIL_OBSERVABILITY_METRICS_FROM_MUST_BE_ON_OR_BEFORE_TO,
            ) from e
        if code == "range_too_large":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=HTTP_DETAIL_OBSERVABILITY_METRICS_RANGE_EXCEEDS_MAX_DAYS,
            ) from e
        raise

    payload = svc.build(
        ObservabilityMetricsFilters(
            created_from=created_from,
            created_to=created_to,
            client_id=(client_id.strip() if client_id and client_id.strip() else None),
            client_supplier_id=(
                client_supplier_id.strip() if client_supplier_id and client_supplier_id.strip() else None
            ),
            provider_name=(provider_name.strip() if provider_name and provider_name.strip() else None),
            model_name=(model_name.strip() if model_name and model_name.strip() else None),
        )
    )
    return ObservabilityMetricsResponse.model_validate(payload)
