"""v3 aisle positions: list, detail."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, Query

from src.api.dependencies import (
    get_get_position_code_scan_evidence_use_case,
    get_get_position_detail_use_case,
    get_list_aisle_positions_use_case,
    get_position_reconciliation_repo,
    get_result_evidence_query_service,
)
from src.api.errors import mapped_http_exception
from src.api.mappers.result_evidence_mapper import (
    artifact_read_model_to_response,
    result_evidence_view_to_response,
)
from src.api.routes.v3.code_scans import _detection_to_response, _run_to_summary
from src.api.schemas.code_scan_schemas import (
    PositionCodeScanEvidenceResponse,
    PositionCodeScanEvidenceSummaryResponse,
)
from src.api.schemas.listing_schemas import compute_total_pages
from src.api.schemas.position_schemas import (
    PositionDetailResponse,
    PositionListResponse,
    PositionRunContextResponse,
    ResultPositionRefResponse,
    ResultsByPositionGroupResponse,
    ResultsByPositionResponse,
)
from src.application.mappers.position_canonical_view import build_position_canonical_view
from src.application.services.display_primary_product import select_display_primary_product
from src.application.services.position_overrides.effective_position_reader import (
    EffectivePositionReader,
)
from src.application.services.position_reconciliation.group_results_by_position import (
    group_summaries_by_position,
)
from src.application.services.position_reconciliation.published_assignment_reader import (
    PublishedPositionAssignmentReader,
)
from src.application.services.position_reconciliation.result_position_enrichment import (
    apply_published_assignment_to_summary,
    matches_position_filters,
)
from src.application.services.result_evidence_query_service import ResultEvidenceQueryService
from src.application.use_cases.positions.get_position_code_scan_evidence import (
    GetPositionCodeScanEvidenceCommand,
    GetPositionCodeScanEvidenceUseCase,
)
from src.application.use_cases.positions.get_position_detail import GetPositionDetailUseCase
from src.application.use_cases.positions.list_aisle_positions import (
    ListAislePositionsCommand,
    ListAislePositionsUseCase,
)
from src.config import load_settings
from src.runtime.app_container import get_app_container

from .shared import (
    evidence_to_response,
    position_to_summary,
    review_to_response,
    technical_snapshot_from_view,
)

router = APIRouter()


@dataclass(frozen=True)
class _ListAislePositionsQuery:
    """Bundled query params for list_aisle_positions (OpenAPI unchanged — wired via Depends)."""

    status: str | None
    needs_review: bool | None
    min_confidence: float | None
    sku_filter: str | None
    page: int
    page_size: int
    sort_by: str
    sort_dir: str
    consolidate_by_sku: bool
    job_id: str | None
    include_technical: bool
    with_position: bool | None
    position_label_id: str | None
    position_assignment_status: str | None
    position_name: str | None
    unassigned_reason: str | None
    position_source: str | None
    has_manual_override: bool | None
    manual_reason_code: str | None
    manual_position_invalidated: bool | None
    automatic_changed_after_override: bool | None


def _list_aisle_positions_query_dep(
    status: str | None = Query(
        None, description="Filter by position status (e.g. detected, reviewed)."
    ),
    needs_review: bool | None = Query(
        None, description="When set, only positions with this needs_review flag."
    ),
    min_confidence: float | None = Query(
        None, ge=0.0, le=1.0, description="Minimum confidence (inclusive)."
    ),
    sku_filter: str | None = Query(
        None, description="Substring match against product SKU for this aisle."
    ),
    page: int = Query(1, ge=1, description="1-based page index after optional SKU consolidation."),
    page_size: int = Query(
        25,
        ge=1,
        le=500,
        description="Page size after optional SKU consolidation (max 500).",
    ),
    sort_by: str = Query(
        "created_at",
        description=(
            "Post-consolidation sort: created_at | updated_at | confidence | sku | quantity | "
            "photo_sequence (requires unmerged rows — SKU merge is disabled automatically for this sort)"
        ),
    ),
    sort_dir: str = Query("asc", description="asc | desc"),
    consolidate_by_sku: bool = Query(
        True,
        description=(
            "When false, skip SKU merge so list rows stay one-to-one with detections (photo review). "
            "Ignored (treated as false) when sort_by=photo_sequence. Default true preserves legacy "
            "consolidated aisle results."
        ),
    ),
    job_id: str | None = Query(
        None,
        description=(
            "Optional inventory job id. Omitted: operational_job_id if set; else legacy null-job rows "
            "only (job_id IS NULL). Explicit job_id always wins."
        ),
    ),
    include_technical: bool = Query(
        False,
        description="When true, include legacy `detected_summary_json` in list rows for transitional/debug clients.",
    ),
    with_position: bool | None = Query(
        None,
        description="Phase 5: when true/false, keep only rows with/without a published aisle position.",
    ),
    position_label_id: str | None = Query(
        None, description="Phase 5: filter by published position label id."
    ),
    position_assignment_status: str | None = Query(
        None, description="Phase 5: filter by assignment status (e.g. ASSIGNED_AUTOMATIC)."
    ),
    position_name: str | None = Query(
        None, description="Phase 5: filter by human position name (case-insensitive)."
    ),
    unassigned_reason: str | None = Query(
        None,
        description="Phase 5: filter by unassigned reason or UNASSIGNED_* status code.",
    ),
    position_source: str | None = Query(
        None, pattern="^(AUTOMATIC|MANUAL|NONE)$"
    ),
    has_manual_override: bool | None = Query(None),
    manual_reason_code: str | None = Query(None),
    manual_position_invalidated: bool | None = Query(None),
    automatic_changed_after_override: bool | None = Query(None),
) -> _ListAislePositionsQuery:
    # One FastAPI Query() per public query param — arity fixed by OpenAPI; cannot merge without changing contract.
    return _ListAislePositionsQuery(
        status=status,
        needs_review=needs_review,
        min_confidence=min_confidence,
        sku_filter=sku_filter.strip() if sku_filter and str(sku_filter).strip() else None,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
        consolidate_by_sku=consolidate_by_sku,
        job_id=job_id.strip() if job_id and str(job_id).strip() else None,
        include_technical=include_technical,
        with_position=with_position,
        position_label_id=(
            position_label_id.strip() if position_label_id and str(position_label_id).strip() else None
        ),
        position_assignment_status=(
            position_assignment_status.strip()
            if position_assignment_status and str(position_assignment_status).strip()
            else None
        ),
        position_name=(
            position_name.strip() if position_name and str(position_name).strip() else None
        ),
        unassigned_reason=(
            unassigned_reason.strip()
            if unassigned_reason and str(unassigned_reason).strip()
            else None
        ),
        position_source=position_source,
        has_manual_override=has_manual_override,
        manual_reason_code=(
            manual_reason_code.strip().upper()
            if manual_reason_code and manual_reason_code.strip()
            else None
        ),
        manual_position_invalidated=manual_position_invalidated,
        automatic_changed_after_override=automatic_changed_after_override,
    )


def _load_assignment_views(
    *,
    reconciliation_repo: Any | None,
    job_id: str | None,
    result_ids: list[str],
) -> dict[str, Any]:
    settings = load_settings()
    if reconciliation_repo is None or not job_id:
        return {}
    reader = PublishedPositionAssignmentReader(
        reconciliation_repo=reconciliation_repo,
        enrichment_enabled=settings.position_results_enrichment_enabled,
    )
    container = get_app_container()
    return EffectivePositionReader(
        automatic_reader=reader,
        override_repo=container.get_manual_position_override_repo(),
        label_repo=container.get_client_position_label_repo(),
    ).load_for_job(job_id, result_ids=result_ids)


def _position_summaries_for_list(
    *,
    result: Any,
    include_technical: bool,
    reconciliation_repo: Any | None = None,
    with_position: bool | None = None,
    position_label_id: str | None = None,
    position_assignment_status: str | None = None,
    position_name: str | None = None,
    unassigned_reason: str | None = None,
    position_source: str | None = None,
    has_manual_override: bool | None = None,
    manual_reason_code: str | None = None,
    manual_position_invalidated: bool | None = None,
    automatic_changed_after_override: bool | None = None,
) -> list[Any]:
    """Build position summary list from list use-case result (Phase 5 enrichment)."""
    settings = load_settings()
    job_id = getattr(result, "resolved_job_id", None)
    result_ids = [p.id for p in result.primary_products if p is not None]
    views = _load_assignment_views(
        reconciliation_repo=reconciliation_repo,
        job_id=job_id,
        result_ids=result_ids,
    )
    filters_on = settings.position_results_filters_enabled and any(
        v is not None
        for v in (
            with_position,
            position_label_id,
            position_assignment_status,
            position_name,
            unassigned_reason,
            position_source,
            has_manual_override,
            manual_reason_code,
            manual_position_invalidated,
            automatic_changed_after_override,
        )
    )
    summaries = []
    products_by_position = getattr(result, "products", ()) or ()
    for idx, (p, primary) in enumerate(zip(result.positions, result.primary_products)):
        primary_id = primary.id if primary is not None else None
        view = views.get(primary_id) if primary_id else None
        if filters_on and not matches_position_filters(
            view,
            with_position=with_position,
            position_label_id=position_label_id,
            position_assignment_status=position_assignment_status,
            position_name=position_name,
            unassigned_reason=unassigned_reason,
            position_source=position_source,
            has_manual_override=has_manual_override,
            manual_reason_code=manual_reason_code,
            manual_position_invalidated=manual_position_invalidated,
            automatic_changed_after_override=automatic_changed_after_override,
        ):
            continue
        corrected_quantity = primary.corrected_quantity if primary is not None else None
        pos_products = (
            products_by_position[idx]
            if idx < len(products_by_position)
            else ()
        )
        summary = position_to_summary(
            p,
            corrected_quantity=corrected_quantity,
            primary_product=primary,
            include_technical_snapshot=include_technical,
            detected_products=pos_products,
        )
        summaries.append(
            apply_published_assignment_to_summary(
                summary,
                primary_product_id=primary_id,
                views_by_result_id=views,
            )
        )
    return summaries


@router.get("/{inventory_id}/aisles/{aisle_id}/positions", response_model=PositionListResponse)
def list_aisle_positions(
    inventory_id: str,
    aisle_id: str,
    use_case: ListAislePositionsUseCase = Depends(get_list_aisle_positions_use_case),
    params: _ListAislePositionsQuery = Depends(_list_aisle_positions_query_dep),
    reconciliation_repo=Depends(get_position_reconciliation_repo),
) -> PositionListResponse:
    """List result positions for an aisle (Aisle Results).

    Filters apply to **raw** rows; ``page`` / ``page_size`` / sort apply **after** optional SKU consolidation
    (see ``consolidate_by_sku``).
    When ``raw_fetch_truncated`` is true in the response, ``total_items`` / ``total_pages`` are only
    reliable within the raw rows the server loaded — not for the entire aisle. See schema docstring.
    """
    try:
        settings = load_settings()
        filters_requested = settings.position_results_filters_enabled and any(
            v is not None
            for v in (
                params.with_position,
                params.position_label_id,
                params.position_assignment_status,
                params.position_name,
                params.unassigned_reason,
                params.position_source,
                params.has_manual_override,
                params.manual_reason_code,
                params.manual_position_invalidated,
                params.automatic_changed_after_override,
            )
        )
        consolidate = params.consolidate_by_sku
        raw_cap = settings.v3_positions_aisle_raw_cap

        # Position filters / full-set enrichment: page through SQL (fetch_all_raw).
        fetch_page = 1 if filters_requested else params.page
        fetch_size = raw_cap if filters_requested else params.page_size
        cmd = ListAislePositionsCommand(
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            status=params.status,
            needs_review=params.needs_review,
            min_confidence=params.min_confidence,
            sku_filter=params.sku_filter,
            page=fetch_page,
            page_size=fetch_size,
            sort_by=params.sort_by,
            sort_dir=params.sort_dir,
            job_id=params.job_id,
            consolidate_by_sku=consolidate,
            fetch_all_raw=filters_requested,
        )
        result = use_case.execute(cmd)
        summaries = _position_summaries_for_list(
            result=result,
            include_technical=params.include_technical,
            reconciliation_repo=reconciliation_repo,
            with_position=params.with_position,
            position_label_id=params.position_label_id,
            position_assignment_status=params.position_assignment_status,
            position_name=params.position_name,
            unassigned_reason=params.unassigned_reason,
            position_source=params.position_source,
            has_manual_override=params.has_manual_override,
            manual_reason_code=params.manual_reason_code,
            manual_position_invalidated=params.manual_position_invalidated,
            automatic_changed_after_override=params.automatic_changed_after_override,
        )
        if filters_requested:
            total_items = len(summaries)
            page = max(1, params.page)
            page_size = max(1, params.page_size)
            start = (page - 1) * page_size
            page_rows = summaries[start : start + page_size]
            return PositionListResponse(
                positions=page_rows,
                page=page,
                page_size=page_size,
                total_items=total_items,
                total_pages=compute_total_pages(total_items, page_size),
                raw_fetch_truncated=result.raw_fetch_truncated or result.total_items >= fetch_size,
                result_job_id=result.resolved_job_id,
                result_context_source=result.result_context_source,
            )
        return PositionListResponse(
            positions=summaries,
            page=result.page,
            page_size=result.page_size,
            total_items=result.total_items,
            total_pages=compute_total_pages(result.total_items, result.page_size),
            raw_fetch_truncated=result.raw_fetch_truncated,
            result_job_id=result.resolved_job_id,
            result_context_source=result.result_context_source,
        )
    except Exception as e:
        # REVISAR_NO_TOCAR: broad catch preserves mapped_http_exception handling for domain errors.
        mapped = mapped_http_exception(e)
        if mapped is not None:
            raise mapped
        raise


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/positions/by-position",
    response_model=ResultsByPositionResponse,
)
def list_aisle_positions_by_position(
    inventory_id: str,
    aisle_id: str,
    use_case: ListAislePositionsUseCase = Depends(get_list_aisle_positions_use_case),
    reconciliation_repo=Depends(get_position_reconciliation_repo),
    job_id: str | None = Query(
        None,
        description="Optional inventory job id (same semantics as GET …/positions).",
    ),
    page_size: int = Query(
        500,
        ge=1,
        le=100_000,
        description=(
            "Max consolidated rows to group. The server loads up to "
            "V3_POSITIONS_AISLE_RAW_CAP raw rows before grouping."
        ),
    ),
) -> ResultsByPositionResponse:
    """Group aisle results by published Phase 4 position (Phase 5). Includes 'Sin posición'."""
    try:
        raw_cap = load_settings().v3_positions_aisle_raw_cap
        fetch_size = raw_cap
        cmd = ListAislePositionsCommand(
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            page=1,
            page_size=fetch_size,
            sort_by="created_at",
            sort_dir="asc",
            job_id=job_id.strip() if job_id and str(job_id).strip() else None,
            consolidate_by_sku=True,
            fetch_all_raw=True,
        )
        result = use_case.execute(cmd)
        summaries = _position_summaries_for_list(
            result=result,
            include_technical=False,
            reconciliation_repo=reconciliation_repo,
        )
        primary_ids = [
            primary.id if primary is not None else None for primary in result.primary_products
        ]
        views = _load_assignment_views(
            reconciliation_repo=reconciliation_repo,
            job_id=result.resolved_job_id,
            result_ids=[pid for pid in primary_ids if pid],
        )
        buckets = group_summaries_by_position(
            summaries,
            views_by_result_id=views,
            primary_product_ids=primary_ids,
        )
        assigned = sum(1 for b in buckets if b.position_name)
        assigned_results = sum(b.product_count for b in buckets if b.position_name)
        unassigned_results = sum(b.product_count for b in buckets if b.position_name is None)
        groups = [
            ResultsByPositionGroupResponse(
                position=(
                    ResultPositionRefResponse(id=b.position_id, name=b.position_name)
                    if b.position_name
                    else None
                ),
                label=b.label,
                product_count=b.product_count,
                total_quantity=b.total_quantity,
                items=list(b.items),
            )
            for b in buckets
        ]
        truncated = bool(result.raw_fetch_truncated) or result.total_items >= fetch_size
        return ResultsByPositionResponse(
            groups=groups,
            result_job_id=result.resolved_job_id,
            result_context_source=result.result_context_source,
            assigned_results_count=assigned_results,
            unassigned_results_count=unassigned_results,
            positions_count=assigned,
            truncated=truncated,
        )
    except Exception as e:
        mapped = mapped_http_exception(e)
        if mapped is not None:
            raise mapped
        raise


@dataclass(frozen=True)
class _PositionDetailQuery:
    explicit_job_id: str | None
    exact_position: bool


def _position_detail_query_dep(
    job_id: str | None = Query(
        None,
        description="Optional; must match resolved result context for this position (Phase 2).",
    ),
    exact_position: bool = Query(
        False,
        description=(
            "When true, return products/evidence for this ``position_id`` only — no redirect to a "
            "SKU-consolidated representative row. Use with photo-accurate aisle review lists."
        ),
    ),
) -> _PositionDetailQuery:
    return _PositionDetailQuery(
        explicit_job_id=job_id.strip() if job_id and str(job_id).strip() else None,
        exact_position=exact_position,
    )


def _build_position_detail_response(
    result: Any,
    *,
    evidence_query: ResultEvidenceQueryService | None = None,
    inventory_id: str | None = None,
    aisle_id: str | None = None,
    reconciliation_repo: Any | None = None,
) -> PositionDetailResponse:
    """Assemble PositionDetailResponse from GetPositionDetailUseCase result."""
    primary_product = select_display_primary_product(result.products)
    corrected_quantity = primary_product.corrected_quantity if primary_product is not None else None
    view = build_position_canonical_view(
        result.position,
        primary_product,
        corrected_quantity=corrected_quantity,
    )
    rc = result.run_context
    resolved_job_id = rc.resolved_job_id or rc.job_id or result.position.job_id
    evidence_view = None
    traceability_artifact = None
    if evidence_query is not None and inventory_id and aisle_id:
        evidence_view = result_evidence_view_to_response(
            evidence_query.get_position_evidence_view(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                position=result.position,
                job_id=resolved_job_id,
            )
        )
        artifact_model = evidence_query.get_traceability_artifact(resolved_job_id)
        traceability_artifact = artifact_read_model_to_response(artifact_model)
    summary = position_to_summary(
        result.position,
        corrected_quantity=corrected_quantity,
        primary_product=primary_product,
        include_technical_snapshot=False,
    )
    primary_id = primary_product.id if primary_product is not None else None
    views = _load_assignment_views(
        reconciliation_repo=reconciliation_repo,
        job_id=resolved_job_id,
        result_ids=[primary_id] if primary_id else [],
    )
    summary = apply_published_assignment_to_summary(
        summary,
        primary_product_id=primary_id,
        views_by_result_id=views,
    )
    return PositionDetailResponse(
        position=summary,
        technical_snapshot=technical_snapshot_from_view(view),
        evidences=[evidence_to_response(e) for e in result.evidences],
        review_actions=[review_to_response(ra) for ra in result.review_actions],
        run_context=PositionRunContextResponse(
            job_id=rc.job_id,
            result_context_source=rc.result_context_source,
            resolved_job_id=rc.resolved_job_id,
            provider_name=rc.provider_name,
            model_name=rc.model_name,
            prompt_key=rc.prompt_key,
            prompt_version=rc.prompt_version,
        ),
        evidence=evidence_view,
        traceability_artifact=traceability_artifact,
    )


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/positions/{position_id}",
    response_model=PositionDetailResponse,
)
def get_position_detail(
    inventory_id: str,
    aisle_id: str,
    position_id: str,
    use_case: GetPositionDetailUseCase = Depends(get_get_position_detail_use_case),
    evidence_query: ResultEvidenceQueryService = Depends(get_result_evidence_query_service),
    reconciliation_repo=Depends(get_position_reconciliation_repo),
    q: _PositionDetailQuery = Depends(_position_detail_query_dep),
) -> PositionDetailResponse:
    """Get detail for the operator-facing current review entity of a position.

    By default the returned ``position`` block follows the same consolidated representative semantics as
    the aisle results list: when ``position_id`` belongs to an aggregated group, detail resolves the
    representative row. Pass ``exact_position=true`` for one-to-one row/evidence traceability.

    **409 Conflict:** When the position exists but its storage ``job_id`` does not match the resolved
    result slice (explicit query param, then ``aisles.operational_job_id``, then legacy null-job
    rows). This avoids returning another run's data without an explicit ``job_id`` override.
    """
    try:
        result = use_case.execute(
            inventory_id,
            aisle_id,
            position_id,
            explicit_job_id=q.explicit_job_id,
            exact_position=q.exact_position,
        )
        return _build_position_detail_response(
            result,
            evidence_query=evidence_query,
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            reconciliation_repo=reconciliation_repo,
        )
    except Exception as e:
        # REVISAR_NO_TOCAR: broad catch preserves mapped_http_exception handling for domain errors.
        mapped = mapped_http_exception(e)
        if mapped is not None:
            raise mapped
        raise


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/positions/{position_id}/code-scan-evidence",
    response_model=PositionCodeScanEvidenceResponse,
)
def get_position_code_scan_evidence(
    inventory_id: str,
    aisle_id: str,
    position_id: str,
    use_case: GetPositionCodeScanEvidenceUseCase = Depends(
        get_get_position_code_scan_evidence_use_case
    ),
) -> PositionCodeScanEvidenceResponse:
    """Read-only code scan detections linked to this position via ``matched_position_id``."""
    try:
        result = use_case.execute(
            GetPositionCodeScanEvidenceCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                position_id=position_id,
            )
        )
    except Exception as e:
        mapped = mapped_http_exception(e)
        if mapped is not None:
            raise mapped
        raise
    latest_run = (
        _run_to_summary(result.latest_run) if result.latest_run is not None else None
    )
    return PositionCodeScanEvidenceResponse(
        latest_run=latest_run,
        summary=PositionCodeScanEvidenceSummaryResponse(
            total_detections=result.summary.total_detections,
            source_assets_count=result.summary.source_assets_count,
            code_types=result.summary.code_types,
        ),
        detections=[_detection_to_response(d) for d in result.detections],
    )
