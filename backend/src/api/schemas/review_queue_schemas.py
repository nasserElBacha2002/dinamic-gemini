"""Review queue list API (Sprint 1.4, Sprint 4.2 summary/filters) — cross-inventory positions needing review."""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.api.schemas.listing_schemas import PageMeta
from src.api.schemas.position_schemas import PositionSummaryResponse


class ReviewQueueSummaryResponse(BaseModel):
    """KPI band for the filtered queue (full population, not just the current page)."""

    pending_review: int = Field(description="Rows matching current filters (= total_items scope).")
    low_confidence: int
    invalid_traceability: int
    qty_zero: int
    missing_evidence: int


class ReviewQueueItemResponse(BaseModel):
    inventory_id: str
    inventory_name: str
    aisle_code: str
    position: PositionSummaryResponse


class ReviewQueueListResponse(PageMeta):
    """GET /api/v3/review-queue/positions — filter/sort/pagination + workload summary."""

    summary: ReviewQueueSummaryResponse
    items: list[ReviewQueueItemResponse]
