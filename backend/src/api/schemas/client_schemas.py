"""v3 Client API schemas (Phase A1 foundation)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from src.api.schemas.listing_schemas import PageMeta


class CreateClientRequest(BaseModel):
    """POST /api/v3/clients body."""

    name: str = Field(..., min_length=1, max_length=255)
    status: Literal["active", "inactive"] = Field("active")


class ClientResponse(BaseModel):
    id: str
    name: str
    status: str
    created_at: datetime
    updated_at: datetime


class PaginatedClientListResponse(PageMeta):
    items: list[ClientResponse]

