"""v3.0 Inventory API schemas (request/response)."""

from pydantic import BaseModel, Field


class CreateInventoryRequest(BaseModel):
    """POST /api/v3/inventories body."""
    name: str = Field(..., min_length=1, max_length=255)


class InventoryResponse(BaseModel):
    """Single inventory in list or create response."""
    id: str
    name: str
    status: str
