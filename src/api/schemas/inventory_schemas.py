"""v3.0 Inventory API schemas (request/response)."""

from pydantic import BaseModel


class CreateInventoryRequest(BaseModel):
    """POST /api/v3/inventories body."""
    name: str


class InventoryResponse(BaseModel):
    """Single inventory in list or create response."""
    id: str
    name: str
    status: str
