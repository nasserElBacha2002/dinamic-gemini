"""v3 analytics API — Phase 5.1 (metrics / quality aggregates)."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.application.dto.analytics_dto import AnalyticsFilters
from src.application.services.analytics_query_service import AnalyticsQueryService
from src.auth.dependencies import get_current_admin

from src.api.dependencies import get_analytics_query_service
from src.api.schemas.analytics_schemas import (
    AnalyticsSummaryResponse,
    AnalyticsTrendsResponse,
    AisleIssueListResponse,
    AisleIssueRowResponse,
    InventoryPerformanceListResponse,
    InventoryPerformanceRowResponse,
    QualityPatternListResponse,
    QualityPatternRowResponse,
    TrendPointResponse,
)

router = APIRouter(
    prefix="/api/v3/analytics",
    tags=["analytics-v3"],
    dependencies=[Depends(get_current_admin)],
)


def _range_to_datetimes(
    date_from: Optional[date],
    date_to: Optional[date],
) -> tuple[Optional[datetime], Optional[datetime]]:
    df = None
    if date_from is not None:
        df = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
    dt = None
    if date_to is not None:
        dt = datetime.combine(date_to, time(23, 59, 59, 999999), tzinfo=timezone.utc)
    if df is not None and dt is not None and df > dt:
        raise HTTPException(status_code=422, detail="date_from must be on or before date_to")
    return df, dt


def _filters(
    date_from: Optional[date],
    date_to: Optional[date],
    inventory_id: Optional[str],
    aisle_id: Optional[str],
) -> AnalyticsFilters:
    df, dt = _range_to_datetimes(date_from, date_to)
    inv = inventory_id.strip() if inventory_id and inventory_id.strip() else None
    aid = aisle_id.strip() if aisle_id and aisle_id.strip() else None
    return AnalyticsFilters(date_from=df, date_to=dt, inventory_id=inv, aisle_id=aid)


@router.get("/summary", response_model=AnalyticsSummaryResponse)
def analytics_summary(
    svc: AnalyticsQueryService = Depends(get_analytics_query_service),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    inventory_id: Optional[str] = Query(None),
    aisle_id: Optional[str] = Query(None),
) -> AnalyticsSummaryResponse:
    f = _filters(date_from, date_to, inventory_id, aisle_id)
    d = svc.summary(f)
    return AnalyticsSummaryResponse(
        auto_acceptance_rate=d.auto_acceptance_rate,
        manual_correction_rate=d.manual_correction_rate,
        invalid_traceability_rate=d.invalid_traceability_rate,
        processing_success_rate=d.processing_success_rate,
        average_review_time_seconds=d.average_review_time_seconds,
        reviewed_results_per_day=d.reviewed_results_per_day,
        notes=list(d.notes),
        period_day_count=d.period_day_count,
        settling_actions_count=d.settling_actions_count,
        positions_in_scope=d.positions_in_scope,
    )


@router.get("/trends", response_model=AnalyticsTrendsResponse)
def analytics_trends(
    svc: AnalyticsQueryService = Depends(get_analytics_query_service),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    inventory_id: Optional[str] = Query(None),
    aisle_id: Optional[str] = Query(None),
) -> AnalyticsTrendsResponse:
    f = _filters(date_from, date_to, inventory_id, aisle_id)
    t = svc.trends(f)

    def map_points(xs):
        return [
            TrendPointResponse(
                period=p.period,
                reviewed_results=p.reviewed_results,
                correction_rate=p.correction_rate,
                processing_success_rate=p.processing_success_rate,
            )
            for p in xs
        ]

    return AnalyticsTrendsResponse(
        reviewed_results_over_time=map_points(t.reviewed_results_over_time),
        correction_rate_over_time=map_points(t.correction_rate_over_time),
        processing_success_over_time=map_points(t.processing_success_over_time),
    )


@router.get("/inventories", response_model=InventoryPerformanceListResponse)
def analytics_inventories(
    svc: AnalyticsQueryService = Depends(get_analytics_query_service),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    inventory_id: Optional[str] = Query(None),
    aisle_id: Optional[str] = Query(None),
) -> InventoryPerformanceListResponse:
    f = _filters(date_from, date_to, inventory_id, aisle_id)
    rows = svc.inventory_performance(f)
    return InventoryPerformanceListResponse(
        items=[
            InventoryPerformanceRowResponse(
                inventory_id=r.inventory_id,
                inventory_name=r.inventory_name,
                inventory_created_at=r.inventory_created_at,
                total_aisles=r.total_aisles,
                total_positions=r.total_positions,
                processed_positions=r.processed_positions,
                review_rate=r.review_rate,
                correction_rate=r.correction_rate,
                invalid_traceability_rate=r.invalid_traceability_rate,
                avg_confidence=r.avg_confidence,
                processing_success_rate=r.processing_success_rate,
            )
            for r in rows
        ]
    )


@router.get("/aisles", response_model=AisleIssueListResponse)
def analytics_aisles(
    svc: AnalyticsQueryService = Depends(get_analytics_query_service),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    inventory_id: Optional[str] = Query(None),
    aisle_id: Optional[str] = Query(None),
) -> AisleIssueListResponse:
    f = _filters(date_from, date_to, inventory_id, aisle_id)
    rows = svc.aisle_issues(f)
    return AisleIssueListResponse(
        items=[
            AisleIssueRowResponse(
                aisle_id=r.aisle_id,
                aisle_code=r.aisle_code,
                inventory_id=r.inventory_id,
                inventory_name=r.inventory_name,
                total_results=r.total_results,
                needs_review_count=r.needs_review_count,
                corrected_count=r.corrected_count,
                invalid_traceability_count=r.invalid_traceability_count,
                low_confidence_count=r.low_confidence_count,
                most_common_issue=r.most_common_issue,
            )
            for r in rows
        ]
    )


@router.get("/quality", response_model=QualityPatternListResponse)
def analytics_quality(
    svc: AnalyticsQueryService = Depends(get_analytics_query_service),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    inventory_id: Optional[str] = Query(None),
    aisle_id: Optional[str] = Query(None),
) -> QualityPatternListResponse:
    f = _filters(date_from, date_to, inventory_id, aisle_id)
    rows = svc.quality_patterns(f)
    return QualityPatternListResponse(
        items=[
            QualityPatternRowResponse(
                issue_type=r.issue_type,
                count=r.count,
                percentage=r.percentage,
                notes=r.notes,
            )
            for r in rows
        ]
    )
