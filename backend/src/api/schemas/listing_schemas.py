"""Shared pagination metadata for v3 list/table endpoints (Sprint 1.4)."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from src.api.schemas.aisle_schemas import AisleResponse
from src.api.schemas.inventory_schemas import InventoryListItemResponse


class PageMeta(BaseModel):
    """Shared pagination fields for v3 list responses (flat JSON: same keys as before inheritance refactor).

    ``total_items`` / ``total_pages`` meaning is endpoint-specific. Inventory and aisle list endpoints
    count the full filtered set in memory. For GET .../positions, totals may be **window-local** when
    ``raw_fetch_truncated`` is true — see ``PositionListResponse``.
    """

    page: int = Field(..., ge=1, description="1-based index of this page.")
    page_size: int = Field(..., ge=1, description="Maximum rows in this page.")
    total_items: int = Field(
        ...,
        ge=0,
        description=(
            "Rows matching list filters before paging. Not always the full physical aisle for "
            "GET .../positions when raw_fetch_truncated is true."
        ),
    )
    total_pages: int = Field(
        ...,
        ge=0,
        description="ceil(total_items / page_size); 0 when total_items is 0. Same caveats as total_items.",
    )


class PaginatedInventoryListResponse(PageMeta):
    """GET /api/v3/inventories — paginated inventory table rows.

    **Contract change (Sprint 1.4):** this endpoint returns an object with ``items`` and pagination
    fields, not a bare JSON array. Clients must read ``items`` (see OpenAPI / schema).
    """

    items: List[InventoryListItemResponse]


class PaginatedAisleListResponse(PageMeta):
    """GET /api/v3/inventories/{inventory_id}/aisles — paginated aisle table rows.

    **Contract change (Sprint 1.4):** response is an object with ``items`` plus pagination fields,
    not a bare JSON array.
    """

    items: List[AisleResponse]


def compute_total_pages(total_items: int, page_size: int) -> int:
    if total_items <= 0:
        return 0
    return (total_items + page_size - 1) // page_size
