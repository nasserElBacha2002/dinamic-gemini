"""v3.0 Inventory API schemas (request/response)."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CreateInventoryRequest(BaseModel):
    """POST /api/v3/inventories body."""
    name: str = Field(..., min_length=1, max_length=255)


class InventoryResponse(BaseModel):
    """Single inventory in get or create response."""
    id: str
    name: str
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class InventoryListItemResponse(BaseModel):
    """GET /api/v3/inventories — one row for inventories table (aggregates for screen-ready lists)."""

    id: str
    name: str
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    aisles_count: int = Field(0, ge=0, description="Number of aisles in this inventory.")
    pending_review_count: int = Field(
        0,
        ge=0,
        description="Positions with needs_review true across all aisles.",
    )
    last_activity_at: Optional[datetime] = Field(
        None,
        description="Latest activity: max of inventory, aisle, and position timestamps.",
    )


class InventoryMetricsResponse(BaseModel):
    """GET /api/v3/inventories/{inventory_id}/metrics response — Épica 9 (§9.6)."""
    total_positions: int = Field(..., description="Total positions across all aisles in the inventory.")
    total_reviewed_positions: int = Field(..., description="Positions in terminal state (reviewed, corrected, deleted).")
    auto_accepted_positions: int = Field(..., description="Positions accepted without change (status=reviewed).")
    corrected_positions: int = Field(..., description="Positions that were corrected.")
    deleted_positions: int = Field(..., description="Positions that were deleted.")
    success_rate: float = Field(..., description="Percentage auto_accepted / total_reviewed (0 if total_reviewed=0).")
    correction_rate: float = Field(..., description="Percentage corrected / total_reviewed (0 if total_reviewed=0).")
    deletion_rate: float = Field(..., description="Percentage deleted / total_reviewed (0 if total_reviewed=0).")


class InventoryVisualReferenceResponse(BaseModel):
    """Single visual reference associated with an inventory.

    Does not expose internal storage paths; use dedicated file/serving endpoints if needed.
    """

    id: str
    inventory_id: str
    filename: str
    mime_type: str
    file_size: int
    created_at: datetime


class InventoryVisualReferenceListResponse(BaseModel):
    """Wrapper for listing inventory visual references."""

    items: list[InventoryVisualReferenceResponse]


class UploadInventoryVisualReferencesResponse(BaseModel):
    """Response for POST /api/v3/inventories/{inventory_id}/visual-references."""

    items: list[InventoryVisualReferenceResponse]
