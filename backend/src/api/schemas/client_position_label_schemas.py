"""API schemas for client-scoped positioning labels."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.domain.client_position_label.entities import ClientPositionLabel


class CreateClientPositionLabelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)


class UpdateClientPositionLabelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)


class InvalidateClientPositionLabelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=512)


class RenderClientPositionLabelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: str = Field(default="PNG", pattern="^(?i)(PDF|PNG)$")
    preset: str = Field(default="MM_100x100")


class ClientPositionLabelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    public_identifier: str
    client_id: str
    name: str
    description: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    available_formats: list[str] = Field(default_factory=lambda: ["PNG", "PDF"])
    signature_status: str | None = None
    invalidated_at: datetime | None = None
    invalidation_reason: str | None = None


class ClientPositionLabelListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ClientPositionLabelResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ClientPositionLabelArtifactResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label_id: str
    format: str
    preset: str
    content_type: str
    file_size_bytes: int
    artifact_hash: str
    created_at: datetime


def client_position_label_to_response(label: ClientPositionLabel) -> ClientPositionLabelResponse:
    return ClientPositionLabelResponse(
        id=label.id,
        public_identifier=label.public_identifier,
        client_id=label.client_id,
        name=label.name,
        description=label.description,
        status=label.status.value,
        created_at=label.created_at,
        updated_at=label.updated_at,
        available_formats=["PNG", "PDF"],
        signature_status=label.signature_status.value,
        invalidated_at=label.invalidated_at,
        invalidation_reason=label.invalidation_reason,
    )
