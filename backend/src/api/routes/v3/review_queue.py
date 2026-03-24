"""v3 cross-inventory review queue (Sprint 1.4)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from src.auth.dependencies import get_current_admin

from src.api.dependencies import get_list_review_queue_use_case, get_product_record_repo
from src.api.schemas.listing_schemas import compute_total_pages
from src.api.schemas.review_queue_schemas import ReviewQueueItemResponse, ReviewQueueListResponse
from src.application.ports.contracts import ReviewQueueQuery
from src.application.ports.repositories import ProductRecordRepository
from src.application.use_cases.list_review_queue import ListReviewQueueUseCase

from .shared import position_to_summary

router = APIRouter(
    prefix="/api/v3/review-queue",
    tags=["review-queue-v3"],
    dependencies=[Depends(get_current_admin)],
)


@router.get("/positions", response_model=ReviewQueueListResponse)
def list_review_queue_positions(
    use_case: ListReviewQueueUseCase = Depends(get_list_review_queue_use_case),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
    inventory_id: Optional[str] = Query(None, description="Restrict to aisles in this inventory."),
    aisle_id: Optional[str] = Query(None, description="Restrict to this aisle."),
    min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0),
    sort_by: str = Query("updated_at", description="updated_at | created_at | confidence"),
    sort_dir: str = Query("desc", description="asc | desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> ReviewQueueListResponse:
    """Positions with ``needs_review`` across inventories (paginated)."""
    q = ReviewQueueQuery(
        inventory_id=inventory_id.strip() if inventory_id and inventory_id.strip() else None,
        aisle_id=aisle_id.strip() if aisle_id and aisle_id.strip() else None,
        min_confidence=min_confidence,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
    )
    rows, total = use_case.execute(q)
    ps = q.page_size
    items: list[ReviewQueueItemResponse] = []
    for row in rows:
        products = product_record_repo.list_by_position(row.position.id)
        primary = sorted(products, key=lambda x: (x.created_at, x.id))[0] if products else None
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
                ),
            )
        )
    return ReviewQueueListResponse(
        items=items,
        page=q.page,
        page_size=ps,
        total_items=total,
        total_pages=compute_total_pages(total, ps),
    )
