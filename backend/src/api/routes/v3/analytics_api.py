"""v3 analytics API — Phase 5.1 (metrics / quality aggregates)."""

from __future__ import annotations

from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.constants.error_wire import (
    HTTP_DETAIL_ANALYTICS_DATE_FROM_MUST_BE_ON_OR_BEFORE_DATE_TO,
)
from src.api.constants.route_paths import API_V3_ANALYTICS_ROUTER_PREFIX
from src.api.dependencies import (
    get_analytics_cost_summary_service,
    get_analytics_query_service,
    get_compare_aisle_runs_use_case,
)
from src.api.errors import mapped_http_exception
from src.api.schemas.analytics_schemas import (
    AisleIssueListResponse,
    AisleIssueRowResponse,
    AnalyticsSummaryResponse,
    AnalyticsTrendsResponse,
    InventoryPerformanceListResponse,
    InventoryPerformanceRowResponse,
    ManualInterventionBreakdownResponse,
    ManualInterventionCategoryResponse,
    QualityPatternListResponse,
    QualityPatternRowResponse,
    TrendPointResponse,
)
from src.api.schemas.analytics_cost_schemas import (
    AnalyticsCostByAisleResponse,
    AnalyticsCostByCaptureStatusResponse,
    AnalyticsCostByInventoryResponse,
    AnalyticsCostByProviderModelResponse,
    AnalyticsCostSummaryResponse,
    AnalyticsCostSummaryScopeResponse,
    AnalyticsCostTotalsResponse,
)
from src.api.schemas.benchmark_schemas import AisleBenchmarkCompareResponse
from src.application.dto.analytics_cost_dto import AnalyticsCostSummaryFilters
from src.application.dto.analytics_dto import AnalyticsFilters
from src.application.services.analytics_cost_summary_service import (
    AnalyticsCostSummaryService,
    resolve_cost_summary_time_range,
)
from src.application.services.analytics_query_service import AnalyticsQueryService
from src.application.use_cases.compare_aisle_runs import (
    CompareAisleRunsCommand,
    CompareAisleRunsUseCase,
)
from src.auth.dependencies import get_current_admin

router = APIRouter(
    prefix=API_V3_ANALYTICS_ROUTER_PREFIX,
    tags=["analytics-v3"],
    dependencies=[Depends(get_current_admin)],
)


def _range_to_datetimes(
    date_from: date | None,
    date_to: date | None,
) -> tuple[datetime | None, datetime | None]:
    df = None
    if date_from is not None:
        df = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
    dt = None
    if date_to is not None:
        dt = datetime.combine(date_to, time(23, 59, 59, 999999), tzinfo=timezone.utc)
    if df is not None and dt is not None and df > dt:
        raise HTTPException(
            status_code=422, detail=HTTP_DETAIL_ANALYTICS_DATE_FROM_MUST_BE_ON_OR_BEFORE_DATE_TO
        )
    return df, dt


def _filters(
    date_from: date | None,
    date_to: date | None,
    inventory_id: str | None,
    aisle_id: str | None,
) -> AnalyticsFilters:
    df, dt = _range_to_datetimes(date_from, date_to)
    inv = inventory_id.strip() if inventory_id and inventory_id.strip() else None
    aid = aisle_id.strip() if aisle_id and aisle_id.strip() else None
    return AnalyticsFilters(date_from=df, date_to=dt, inventory_id=inv, aisle_id=aid)


def _analytics_filters_validated(
    svc: AnalyticsQueryService,
    date_from: date | None,
    date_to: date | None,
    inventory_id: str | None,
    aisle_id: str | None,
) -> AnalyticsFilters:
    f = _filters(date_from, date_to, inventory_id, aisle_id)
    try:
        svc.validate_scope(f)
    except Exception as e:
        mapped = mapped_http_exception(e)
        if mapped is not None:
            raise mapped
        raise
    return f


def _decimal_to_float(value) -> float | None:
    if value is None:
        return None
    return float(value)


def _cost_filters(
    date_from: date | None,
    date_to: date | None,
    inventory_id: str | None,
    aisle_id: str | None,
    client_id: str | None,
    client_supplier_id: str | None,
    provider_name: str | None,
    model_name: str | None,
) -> AnalyticsCostSummaryFilters:
    df, dt = _range_to_datetimes(date_from, date_to)
    try:
        finished_from, finished_to = resolve_cost_summary_time_range(df, dt)
    except ValueError as e:
        code = str(e)
        if code == "from_after_to":
            raise HTTPException(
                status_code=422, detail=HTTP_DETAIL_ANALYTICS_DATE_FROM_MUST_BE_ON_OR_BEFORE_DATE_TO
            ) from e
        if code == "range_too_large":
            raise HTTPException(status_code=422, detail="date_range_exceeds_maximum_window") from e
        raise
    return AnalyticsCostSummaryFilters(
        finished_from=finished_from,
        finished_to=finished_to,
        inventory_id=inventory_id.strip() if inventory_id and inventory_id.strip() else None,
        aisle_id=aisle_id.strip() if aisle_id and aisle_id.strip() else None,
        client_id=client_id.strip() if client_id and client_id.strip() else None,
        client_supplier_id=client_supplier_id.strip()
        if client_supplier_id and client_supplier_id.strip()
        else None,
        provider_name=provider_name.strip() if provider_name and provider_name.strip() else None,
        model_name=model_name.strip() if model_name and model_name.strip() else None,
    )


@router.get("/cost-summary", response_model=AnalyticsCostSummaryResponse)
def analytics_cost_summary(
    svc: AnalyticsCostSummaryService = Depends(get_analytics_cost_summary_service),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    inventory_id: str | None = Query(None),
    aisle_id: str | None = Query(None),
    client_id: str | None = Query(None),
    client_supplier_id: str | None = Query(None),
    provider_name: str | None = Query(None),
    model_name: str | None = Query(None),
) -> AnalyticsCostSummaryResponse:
    """Aggregate LLM processing cost and counted quantity for the analytics dashboard.

    **Cost semantics:** sums persisted ``result_json.llm_cost_snapshot.computed_cost.total_cost``
    only when finite and non-negative. Jobs without a valid snapshot are counted separately.

    **Time window:** terminal aisle jobs whose ``finished_at`` falls in the resolved range
    (default last 30 days, max 90). The underlying job query caps rows by ``created_at`` in the
    same window (see ``DATE_RANGE_CAPPED`` warning when the cap is hit).

    **Counted quantity:** operational UI/export rollup per aisle in scope; null when unavailable.
    """
    filters = _cost_filters(
        date_from,
        date_to,
        inventory_id,
        aisle_id,
        client_id,
        client_supplier_id,
        provider_name,
        model_name,
    )
    try:
        svc.validate_scope(filters)
    except Exception as e:
        mapped = mapped_http_exception(e)
        if mapped is not None:
            raise mapped
        raise
    data = svc.build(filters)
    return AnalyticsCostSummaryResponse(
        scope=AnalyticsCostSummaryScopeResponse.model_validate(data.scope.__dict__),
        totals=AnalyticsCostTotalsResponse(
            jobs_total=data.totals.jobs_total,
            jobs_with_cost=data.totals.jobs_with_cost,
            jobs_without_cost=data.totals.jobs_without_cost,
            jobs_with_exact_cost=data.totals.jobs_with_exact_cost,
            jobs_with_estimated_cost=data.totals.jobs_with_estimated_cost,
            jobs_with_partial_cost=data.totals.jobs_with_partial_cost,
            jobs_with_unavailable_cost=data.totals.jobs_with_unavailable_cost,
            jobs_with_missing_cost=data.totals.jobs_with_missing_cost,
            total_cost=_decimal_to_float(data.totals.total_cost),
            total_counted_quantity=data.totals.total_counted_quantity,
            cost_per_counted_unit=_decimal_to_float(data.totals.cost_per_counted_unit),
            total_execution_time_seconds=data.totals.total_execution_time_seconds,
            average_execution_time_seconds=data.totals.average_execution_time_seconds,
        ),
        by_provider_model=[
            AnalyticsCostByProviderModelResponse(
                provider_name=r.provider_name,
                model_name=r.model_name,
                jobs_total=r.jobs_total,
                jobs_with_cost=r.jobs_with_cost,
                total_cost=_decimal_to_float(r.total_cost),
                total_counted_quantity=r.total_counted_quantity,
                cost_per_counted_unit=_decimal_to_float(r.cost_per_counted_unit),
                average_execution_time_seconds=r.average_execution_time_seconds,
            )
            for r in data.by_provider_model
        ],
        by_inventory=[
            AnalyticsCostByInventoryResponse(
                inventory_id=r.inventory_id,
                inventory_name=r.inventory_name,
                jobs_total=r.jobs_total,
                jobs_with_cost=r.jobs_with_cost,
                total_cost=_decimal_to_float(r.total_cost),
                total_counted_quantity=r.total_counted_quantity,
                cost_per_counted_unit=_decimal_to_float(r.cost_per_counted_unit),
                total_execution_time_seconds=r.total_execution_time_seconds,
            )
            for r in data.by_inventory
        ],
        by_aisle=[
            AnalyticsCostByAisleResponse(
                inventory_id=r.inventory_id,
                inventory_name=r.inventory_name,
                aisle_id=r.aisle_id,
                aisle_code=r.aisle_code,
                jobs_total=r.jobs_total,
                jobs_with_cost=r.jobs_with_cost,
                total_cost=_decimal_to_float(r.total_cost),
                total_counted_quantity=r.total_counted_quantity,
                cost_per_counted_unit=_decimal_to_float(r.cost_per_counted_unit),
                total_execution_time_seconds=r.total_execution_time_seconds,
            )
            for r in data.by_aisle
        ],
        by_capture_status=[
            AnalyticsCostByCaptureStatusResponse(
                capture_status=r.capture_status,
                jobs_total=r.jobs_total,
                total_cost=_decimal_to_float(r.total_cost),
            )
            for r in data.by_capture_status
        ],
        warnings=list(data.warnings),
    )


@router.get("/summary", response_model=AnalyticsSummaryResponse)
def analytics_summary(
    svc: AnalyticsQueryService = Depends(get_analytics_query_service),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    inventory_id: str | None = Query(None),
    aisle_id: str | None = Query(None),
) -> AnalyticsSummaryResponse:
    """Return additive KPIs for the analytics dashboard.

    **Multi-run:** position-in-scope counts include **all** non-deleted position rows matching
    inventory/aisle filters — not the single “resolved slice” per aisle used by Aisle Results
    (``operational_job_id`` / legacy / explicit ``job_id``). Summary ``notes`` include a reminder;
    aligning dashboard aggregates with per-run operational semantics is deferred.

    ``operator_marked_unknown_*`` fields are populated only from the explicit persisted terminal
    operator outcome. ``unidentified_product_*`` fields are driven by the display-primary product
    row having ``sku='UNKNOWN'``. Historical rows with ``review_resolution = NULL`` are left out of
    operator-marked unknown counts in this phase.
    ``invalid`` remains separate and is still derived only from traceability/state metrics, not from
    a dedicated terminal review outcome.
    """
    f = _analytics_filters_validated(svc, date_from, date_to, inventory_id, aisle_id)
    d = svc.summary(f)
    return AnalyticsSummaryResponse(
        auto_acceptance_rate=d.auto_acceptance_rate,
        manual_correction_rate=d.manual_correction_rate,
        operator_marked_unknown_rate=d.operator_marked_unknown_rate,
        operator_marked_unknown_count=d.operator_marked_unknown_count,
        unidentified_product_rate=d.unidentified_product_rate,
        unidentified_product_count=d.unidentified_product_count,
        unknown_rate=d.unknown_rate,
        unknown_count=d.unknown_count,
        invalid_traceability_rate=d.invalid_traceability_rate,
        processing_success_rate=d.processing_success_rate,
        average_processing_time_seconds=d.average_processing_time_seconds,
        average_processing_time_minutes=d.average_processing_time_minutes,
        settling_actions_per_day=d.settling_actions_per_day,
        notes=list(d.notes),
        period_day_count=d.period_day_count,
        settling_actions_count=d.settling_actions_count,
        positions_in_scope=d.positions_in_scope,
        total_positions_in_scope=d.total_positions_in_scope,
        processed_positions_count=d.processed_positions_count,
        reviewed_positions_count=d.reviewed_positions_count,
    )


@router.get("/trends", response_model=AnalyticsTrendsResponse)
def analytics_trends(
    svc: AnalyticsQueryService = Depends(get_analytics_query_service),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    inventory_id: str | None = Query(None),
    aisle_id: str | None = Query(None),
) -> AnalyticsTrendsResponse:
    f = _analytics_filters_validated(svc, date_from, date_to, inventory_id, aisle_id)
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
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    inventory_id: str | None = Query(None),
    aisle_id: str | None = Query(None),
) -> InventoryPerformanceListResponse:
    f = _analytics_filters_validated(svc, date_from, date_to, inventory_id, aisle_id)
    rows = svc.inventory_performance(f)
    return InventoryPerformanceListResponse(
        items=[
            InventoryPerformanceRowResponse(
                inventory_id=r.inventory_id,
                inventory_name=r.inventory_name,
                inventory_created_at=r.inventory_created_at,
                total_aisles=r.total_aisles,
                aisles_count=r.aisles_count,
                total_positions=r.total_positions,
                positions_count=r.positions_count,
                processed_positions=r.processed_positions,
                processed_count=r.processed_count,
                review_rate=r.review_rate,
                correction_rate=r.correction_rate,
                auto_acceptance_rate=r.auto_acceptance_rate,
                manual_correction_rate=r.manual_correction_rate,
                operator_marked_unknown_rate=r.operator_marked_unknown_rate,
                unidentified_product_rate=r.unidentified_product_rate,
                unknown_rate=r.unknown_rate,
                invalid_traceability_rate=r.invalid_traceability_rate,
                avg_confidence=r.avg_confidence,
                processing_success_rate=r.processing_success_rate,
                average_processing_time_minutes=r.average_processing_time_minutes,
            )
            for r in rows
        ]
    )


@router.get("/aisles", response_model=AisleIssueListResponse)
def analytics_aisles(
    svc: AnalyticsQueryService = Depends(get_analytics_query_service),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    inventory_id: str | None = Query(None),
    aisle_id: str | None = Query(None),
) -> AisleIssueListResponse:
    f = _analytics_filters_validated(svc, date_from, date_to, inventory_id, aisle_id)
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
                operator_marked_unknown_count=r.operator_marked_unknown_count,
                unidentified_product_count=r.unidentified_product_count,
                unknown_count=r.unknown_count,
                manual_corrections_count=r.manual_corrections_count,
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
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    inventory_id: str | None = Query(None),
    aisle_id: str | None = Query(None),
) -> QualityPatternListResponse:
    f = _analytics_filters_validated(svc, date_from, date_to, inventory_id, aisle_id)
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


@router.get("/manual-interventions", response_model=ManualInterventionBreakdownResponse)
def analytics_manual_interventions(
    svc: AnalyticsQueryService = Depends(get_analytics_query_service),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    inventory_id: str | None = Query(None),
    aisle_id: str | None = Query(None),
) -> ManualInterventionBreakdownResponse:
    """Return current persisted manual intervention categories for the analytics scope.

    Date filters apply to review action timestamps. Operator-marked unknown is exposed only when
    backed by the explicit persisted terminal review model. Invalid remains unavailable until
    persisted separately from delete_position. Historical rows with ``review_resolution = NULL``
    are not heuristically backfilled into operator-marked unknown.
    """
    f = _analytics_filters_validated(svc, date_from, date_to, inventory_id, aisle_id)
    data = svc.manual_intervention_breakdown(f)
    return ManualInterventionBreakdownResponse(
        reviewed_positions_count=data.reviewed_positions_count,
        intervention_positions_count=data.intervention_positions_count,
        items=[
            ManualInterventionCategoryResponse(
                category=item.category,
                count=item.count,
                percentage=item.percentage,
                available=item.available,
                notes=item.notes,
            )
            for item in data.items
        ],
        notes=list(data.notes),
    )


@router.get(
    "/benchmark/inventories/{inventory_id}/aisles/{aisle_id}/compare",
    response_model=AisleBenchmarkCompareResponse,
)
def analytics_benchmark_compare_aisle_runs(
    inventory_id: str,
    aisle_id: str,
    job_a_id: str = Query(..., alias="job_a_id", min_length=1),
    job_b_id: str = Query(..., alias="job_b_id", min_length=1),
    use_case: CompareAisleRunsUseCase = Depends(get_compare_aisle_runs_use_case),
) -> AisleBenchmarkCompareResponse:
    """Phase 6 — same payload as ``GET /api/v3/inventories/.../benchmark/compare`` (benchmark-only).

    Exposed under ``/analytics`` so operational KPI routes stay conceptually separate from
    explicit multi-run inspection workflows.
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
        mapped = mapped_http_exception(e)
        if mapped is not None:
            raise mapped
        raise
