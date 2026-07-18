"""v3 Client API schemas (Phase A1 foundation)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from src.api.schemas.identification_mode_literals import (
    IdentificationModeLiteral,
    IdentificationModeSourceLiteral,
)
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
    #: Configured local default; null means inherit system default.
    identification_mode: IdentificationModeLiteral | None = None
    effective_identification_mode: IdentificationModeLiteral
    identification_mode_source: IdentificationModeSourceLiteral


class UpdateClientRequest(BaseModel):
    """PATCH /api/v3/clients/{client_id} — partial update."""

    name: str | None = Field(None, min_length=1, max_length=255)
    identification_mode: IdentificationModeLiteral | None = Field(
        None,
        description="Set client default identification mode; send null to clear (inherit system default).",
    )

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> UpdateClientRequest:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class PaginatedClientListResponse(PageMeta):
    items: list[ClientResponse]
