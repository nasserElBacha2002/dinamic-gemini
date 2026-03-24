"""v3.0 Aisle API schemas (request/response)."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CreateAisleRequest(BaseModel):
    """POST /api/v3/inventories/{inventory_id}/aisles body."""
    code: str = Field(..., min_length=1, max_length=64)


class AisleJobSummary(BaseModel):
    """Latest job summary for an aisle (optional in list response). Aligned with JobSummary for list/status contract."""
    id: str
    status: str
    created_at: datetime
    updated_at: datetime
    error_message: Optional[str] = None


class AisleResponse(BaseModel):
    """Single aisle in list or create response.

    List (GET .../aisles) includes ``assets_count``, ``positions_count``,
    ``pending_review_positions_count``, and ``last_activity_at`` for the Inventory Detail table.
    Create returns these as 0 / null when not computed.
    """

    id: str
    inventory_id: str
    code: str
    status: str
    created_at: datetime
    updated_at: datetime
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    latest_job: Optional[AisleJobSummary] = None
    assets_count: int = 0
    positions_count: int = 0
    pending_review_positions_count: int = 0
    last_activity_at: Optional[datetime] = None
