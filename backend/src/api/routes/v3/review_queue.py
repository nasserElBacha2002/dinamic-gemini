"""v3 cross-inventory review queue (Sprint 1.4, Sprint 4.2)."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, Depends, Query

from src.api.constants.route_paths import API_V3_REVIEW_QUEUE_ROUTER_PREFIX
from src.api.dependencies import get_list_review_queue_use_case
from src.api.schemas.listing_schemas import compute_total_pages
from src.api.schemas.review_queue_schemas import (
    ReviewQueueItemResponse,
    ReviewQueueListResponse,
    ReviewQueueSummaryResponse,
)
from src.application.ports.contracts import ReviewQueueQuery
from src.application.use_cases.list_review_queue import ListReviewQueueUseCase
from src.auth.dependencies import get_current_admin

from .shared import position_to_summary

router = APIRouter(
    prefix=API_V3_REVIEW_QUEUE_ROUTER_PREFIX,
    tags=["review-queue-v3"],
    dependencies=[Depends(get_current_admin)],
)


def _strip_opt(s: str | None) -> str | None:
    if s is None:
        return None
    t = str(s).strip()
    return t if t else None


@dataclass(frozen=True)
class _ReviewQueueRouteQuery:
    """Bundled query params for list_review_queue_positions (OpenAPI unchanged — wired via Depends)."""

    inventory_id: str | None
    aisle_id: str | None
    min_confidence: float | None
    max_confidence: float | None
    traceability: str | None
    has_evidence: bool | None
    qty_zero: bool | None
    sku_contains: str | None
    position_status: str | None
    sort_by: str
    sort_dir: str
    page: int
    page_size: int


def _review_queue_query_dep(  # noqa: PLR0913
    inventory_id: str | None = Query(None, description="Restrict to aisles in this inventory."),
    aisle_id: str | None = Query(None, description="Restrict to this aisle."),
    min_confidence: float | None = Query(None, ge=0.0, le=1.0),
    max_confidence: float | None = Query(None, ge=0.0, le=1.0),
    traceability: str | None = Query(
        None,
        description="valid | missing | invalid | unvalidated",
    ),
    has_evidence: bool | None = Query(None),
    qty_zero: bool | None = Query(None),
    sku_contains: str | None = Query(
        None,
        description="Case-insensitive substring on canonical display SKU (snapshot fallback only when needed).",
    ),
    position_status: str | None = Query(
        None,
        description="detected | reviewed | corrected | deleted | confirmed (reviewed or corrected).",
    ),
    sort_by: str = Query("priority", description="priority | updated_at | created_at | confidence"),
    sort_dir: str = Query("desc", description="asc | desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> _ReviewQueueRouteQuery:
    # One FastAPI Query() per public query param — arity fixed by OpenAPI.
    return _ReviewQueueRouteQuery(
        inventory_id=_strip_opt(inventory_id),
        aisle_id=_strip_opt(aisle_id),
        min_confidence=min_confidence,
        max_confidence=max_confidence,
        traceability=_strip_opt(traceability),
        has_evidence=has_evidence,
        qty_zero=qty_zero,
        sku_contains=_strip_opt(sku_contains),
        position_status=_strip_opt(position_status),
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
    )


def _to_review_queue_query(p: _ReviewQueueRouteQuery) -> ReviewQueueQuery:
    return ReviewQueueQuery(
        inventory_id=p.inventory_id,
        aisle_id=p.aisle_id,
        min_confidence=p.min_confidence,
        max_confidence=p.max_confidence,
        traceability=p.traceability,
        has_evidence=p.has_evidence,
        qty_zero=p.qty_zero,
        sku_contains=p.sku_contains,
        position_status=p.position_status,
        sort_by=p.sort_by,
        sort_dir=p.sort_dir,
        page=p.page,
        page_size=p.page_size,
    )


def _review_queue_items(rows: list) -> list[ReviewQueueItemResponse]:
    items: list[ReviewQueueItemResponse] = []
    for row in rows:
        primary = row.primary_product
        corrected_quantity = primary.corrected_quantity if primary is not None else None
        items.append(
            ReviewQueueItemResponse(
                inventory_id=row.inventory_id,
                inventory_name=row.inventory_name,
                aisle_code=row.aisle_code,
                position=position_to_summary(
                    row.position,
                    corrected_quantity=corrected_quantity,
                    primary_product=primary,
                    include_technical_snapshot=False,
                ),
            )
        )
    return items


@router.get("/positions", response_model=ReviewQueueListResponse)
def list_review_queue_positions(
    use_case: ListReviewQueueUseCase = Depends(get_list_review_queue_use_case),
    rq: _ReviewQueueRouteQuery = Depends(_review_queue_query_dep),
) -> ReviewQueueListResponse:
    """Review queue: positions with ``needs_review``, narrowable by status and quality filters (paginated).

    Sprint 4.2: KPI summary, advanced filters, ``sort_by=priority`` (explainable tiers).
    ``sku_contains`` matches canonical display SKU (substring, not full-text search), with
    snapshot fallback only for legacy/aggregated cases where no clearer canonical source exists.
    """
    q = _to_review_queue_query(rq)
    rows, total, summary = use_case.execute(q)
    ps = q.page_size
    return ReviewQueueListResponse(
        summary=ReviewQueueSummaryResponse(
            pending_review=summary.pending_review,
            low_confidence=summary.low_confidence,
            invalid_traceability=summary.invalid_traceability,
            qty_zero=summary.qty_zero,
            missing_evidence=summary.missing_evidence,
        ),
        items=_review_queue_items(rows),
        page=q.page,
        page_size=ps,
        total_items=total,
        total_pages=compute_total_pages(total, ps),
    )
