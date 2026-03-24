"""Review queue list API (Sprint 1.4) — cross-inventory positions needing review."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel

from src.api.schemas.listing_schemas import PageMeta
from src.api.schemas.position_schemas import PositionSummaryResponse


class ReviewQueueItemResponse(BaseModel):
    inventory_id: str
    inventory_name: str
    aisle_code: str
    position: PositionSummaryResponse


class ReviewQueueListResponse(PageMeta):
    """GET /api/v3/review-queue/positions — filter/sort/pagination only; no free-text search yet."""

    items: List[ReviewQueueItemResponse]
