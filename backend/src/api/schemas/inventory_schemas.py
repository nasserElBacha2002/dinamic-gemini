"""v3.0 Inventory API schemas (request/response)."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CreateInventoryRequest(BaseModel):
    """POST /api/v3/inventories body."""
    name: str = Field(..., min_length=1, max_length=255)


class InventoryResponse(BaseModel):
    """Single inventory in list or create response."""
    id: str
    name: str
    status: str
    created_at: Optional[datetime] = None


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
