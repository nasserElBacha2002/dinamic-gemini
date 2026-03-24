"""Review queue list API (Sprint 1.4) — cross-inventory positions needing review."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from src.api.schemas.position_schemas import PositionSummaryResponse


class ReviewQueueItemResponse(BaseModel):
    inventory_id: str
    inventory_name: str
    aisle_code: str
    position: PositionSummaryResponse


class ReviewQueueListResponse(BaseModel):
    items: List[ReviewQueueItemResponse]
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1)
    total_items: int = Field(..., ge=0)
    total_pages: int = Field(..., ge=0)
