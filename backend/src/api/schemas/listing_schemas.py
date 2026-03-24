"""Shared pagination metadata for v3 list/table endpoints (Sprint 1.4)."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from src.api.schemas.aisle_schemas import AisleResponse
from src.api.schemas.inventory_schemas import InventoryListItemResponse


class PageMeta(BaseModel):
    """Stable pagination block for data-heavy tables."""

    page: int = Field(..., ge=1, description="1-based page index.")
    page_size: int = Field(..., ge=1, description="Items per page.")
    total_items: int = Field(..., ge=0, description="Total rows matching filters (before current page slice).")
    total_pages: int = Field(..., ge=0, description="Ceiling of total_items / page_size; 0 when total_items is 0.")


class PaginatedInventoryListResponse(BaseModel):
    """GET /api/v3/inventories — paginated screen-ready inventory rows."""

    items: List[InventoryListItemResponse]
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1)
    total_items: int = Field(..., ge=0)
    total_pages: int = Field(..., ge=0)


class PaginatedAisleListResponse(BaseModel):
    """GET .../inventories/{id}/aisles — paginated aisle rows."""

    items: List[AisleResponse]
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1)
    total_items: int = Field(..., ge=0)
    total_pages: int = Field(..., ge=0)


def compute_total_pages(total_items: int, page_size: int) -> int:
    if total_items <= 0:
        return 0
    return (total_items + page_size - 1) // page_size
