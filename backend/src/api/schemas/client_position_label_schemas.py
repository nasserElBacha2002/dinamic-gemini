"""API schemas for client-scoped positioning labels."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.client_position_label.entities import ClientPositionLabel
from src.domain.client_position_label.hierarchy import PositionHierarchy, PositionSide


class CreateClientPositionLabelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    pallet: str | None = Field(default=None, max_length=64)
    side: str | None = Field(default=None, max_length=8)
    level: int | None = Field(default=None, ge=1)
    marker_index: int | None = Field(default=None, ge=1)
    marker_total: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _require_name_or_hierarchy(self) -> CreateClientPositionLabelRequest:
        hierarchy_fields = (
            self.pallet,
            self.side,
            self.level,
            self.marker_index,
            self.marker_total,
        )
        has_any = any(
            v is not None and (not isinstance(v, str) or v.strip()) for v in hierarchy_fields
        )
        has_all = all(
            v is not None and (not isinstance(v, str) or v.strip()) for v in hierarchy_fields
        )
        if has_any and not has_all:
            raise ValueError(
                "pallet, side, level, marker_index, and marker_total must all be provided together"
            )
        if not has_all and not (self.name or "").strip():
            raise ValueError("name is required when hierarchy is not provided")
        return self


class CreateClientPositionMarkerSetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pallet: str = Field(..., min_length=1, max_length=64)
    side: str = Field(..., min_length=1, max_length=8)
    level: int = Field(..., ge=1)
    marker_total: int = Field(..., ge=1, le=99)
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
    pallet: str | None = None
    side: str | None = None
    level: int | None = None
    marker_index: int | None = None
    marker_total: int | None = None
    marker: str | None = None


class ClientPositionLabelListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ClientPositionLabelResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ClientPositionLabelMarkerSetResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ClientPositionLabelResponse]


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


def _formatted_marker(label: ClientPositionLabel) -> str | None:
    if (
        label.pallet is None
        or label.side is None
        or label.level is None
        or label.marker_index is None
        or label.marker_total is None
    ):
        return None
    try:
        hierarchy = PositionHierarchy(
            pallet=label.pallet,
            side=PositionSide(str(label.side).strip().upper()),
            level=int(label.level),
            marker_index=int(label.marker_index),
            marker_total=int(label.marker_total),
        )
    except (TypeError, ValueError):
        return None
    return hierarchy.formatted_marker_pair()


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
        pallet=label.pallet,
        side=label.side,
        level=label.level,
        marker_index=label.marker_index,
        marker_total=label.marker_total,
        marker=_formatted_marker(label),
    )
