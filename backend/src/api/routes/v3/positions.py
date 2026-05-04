"""v3 aisle positions: list, detail."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, Query

from src.api.dependencies import (
    get_get_position_detail_use_case,
    get_list_aisle_positions_use_case,
)
from src.api.errors import mapped_http_exception
from src.api.schemas.listing_schemas import compute_total_pages
from src.api.schemas.position_schemas import (
    PositionDetailResponse,
    PositionListResponse,
    PositionRunContextResponse,
)
from src.application.mappers.position_canonical_view import build_position_canonical_view
from src.application.services.display_primary_product import select_display_primary_product
from src.application.use_cases.get_position_detail import GetPositionDetailUseCase
from src.application.use_cases.list_aisle_positions import (
    ListAislePositionsCommand,
    ListAislePositionsUseCase,
)

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


def _list_aisle_positions_query_dep(  # noqa: PLR0913
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
    )


def _position_summaries_for_list(
    *,
    result: Any,
    include_technical: bool,
) -> list[Any]:
    """Build position summary list from list use-case result."""
    summaries = []
    for p, primary in zip(result.positions, result.primary_products):
        corrected_quantity = primary.corrected_quantity if primary is not None else None
        summaries.append(
            position_to_summary(
                p,
                corrected_quantity=corrected_quantity,
                primary_product=primary,
                include_technical_snapshot=include_technical,
            )
        )
    return summaries


@router.get("/{inventory_id}/aisles/{aisle_id}/positions", response_model=PositionListResponse)
def list_aisle_positions(
    inventory_id: str,
    aisle_id: str,
    use_case: ListAislePositionsUseCase = Depends(get_list_aisle_positions_use_case),
    params: _ListAislePositionsQuery = Depends(_list_aisle_positions_query_dep),
) -> PositionListResponse:
    """List result positions for an aisle (Aisle Results).

    Filters apply to **raw** rows; ``page`` / ``page_size`` / sort apply **after** optional SKU consolidation
    (see ``consolidate_by_sku``).
    When ``raw_fetch_truncated`` is true in the response, ``total_items`` / ``total_pages`` are only
    reliable within the raw rows the server loaded — not for the entire aisle. See schema docstring.
    """
    try:
        cmd = ListAislePositionsCommand(
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            status=params.status,
            needs_review=params.needs_review,
            min_confidence=params.min_confidence,
            sku_filter=params.sku_filter,
            page=params.page,
            page_size=params.page_size,
            sort_by=params.sort_by,
            sort_dir=params.sort_dir,
            job_id=params.job_id,
            consolidate_by_sku=params.consolidate_by_sku,
        )
        result = use_case.execute(cmd)
        summaries = _position_summaries_for_list(
            result=result,
            include_technical=params.include_technical,
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


def _build_position_detail_response(result: Any) -> PositionDetailResponse:
    """Assemble PositionDetailResponse from GetPositionDetailUseCase result."""
    primary_product = select_display_primary_product(result.products)
    corrected_quantity = primary_product.corrected_quantity if primary_product is not None else None
    view = build_position_canonical_view(
        result.position,
        primary_product,
        corrected_quantity=corrected_quantity,
    )
    rc = result.run_context
    return PositionDetailResponse(
        position=position_to_summary(
            result.position,
            corrected_quantity=corrected_quantity,
            primary_product=primary_product,
            include_technical_snapshot=False,
        ),
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
        return _build_position_detail_response(result)
    except Exception as e:
        # REVISAR_NO_TOCAR: broad catch preserves mapped_http_exception handling for domain errors.
        mapped = mapped_http_exception(e)
        if mapped is not None:
            raise mapped
        raise
