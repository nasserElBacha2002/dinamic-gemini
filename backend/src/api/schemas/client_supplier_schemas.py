"""v3 Client Supplier API schemas (Phase A2 foundation)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from src.api.schemas.listing_schemas import PageMeta


class CreateClientSupplierRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    status: Literal["active", "inactive"] = Field("active")


class ClientSupplierResponse(BaseModel):
    id: str
    client_id: str
    name: str
    status: str
    created_at: datetime
    updated_at: datetime


class PaginatedClientSupplierListResponse(PageMeta):
    items: list[ClientSupplierResponse]

