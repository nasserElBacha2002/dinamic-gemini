"""v3 aisle location + positioning label API schemas (Phase 1)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.api.schemas.listing_schemas import PageMeta
from src.domain.aisle_location.entities import AisleLocation
from src.domain.aisle_location.label_entities import AisleLocationLabel

AisleLocationStatusLiteral = Literal["ACTIVE", "INACTIVE"]


class CreateAisleLocationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., min_length=1, max_length=128)
    display_name: str | None = Field(None, max_length=256)
    description: str | None = Field(None, max_length=2000)


class UpdateAisleLocationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(None, max_length=256)
    description: str | None = Field(None, max_length=2000)
    status: AisleLocationStatusLiteral | None = None


class IssueAisleLocationLabelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str | None = Field(None, max_length=128)


class InvalidateAisleLocationLabelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(None, max_length=500)


class RenderAisleLocationLabelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["PDF", "PNG"] = "PNG"
    preset: str = Field("MM_100x100", min_length=1, max_length=32)


class ReplaceAisleLocationLabelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str | None = Field(None, max_length=128)


class BatchRenderAisleLocationLabelsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preset: str = Field("MM_100x100", min_length=1, max_length=32)
    format: Literal["PDF"] = "PDF"
    location_ids: list[str] | None = None
    emit_missing: bool = False
    idempotency_key: str | None = Field(None, max_length=128)


class AisleLocationLabelArtifactResponse(BaseModel):
    """Public artifact metadata — never exposes storage_key/bucket."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label_id: str
    format: str
    preset: str
    template_version: int
    marker_version: int
    content_type: str
    file_size_bytes: int
    artifact_hash: str
    created_at: datetime


class AisleLocationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    client_id: str
    aisle_id: str
    code: str
    normalized_code: str
    status: str
    created_at: datetime
    updated_at: datetime
    display_name: str | None = None
    description: str | None = None
    created_by: str | None = None
    public_identifier: str = ""


class AisleLocationListResponse(PageMeta):
    items: list[AisleLocationResponse]


class AisleLocationLabelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    client_id: str
    location_id: str
    public_identifier: str
    payload_version: int
    marker_version: int
    template_version: int
    status: str
    payload: dict[str, Any]
    generated_at: datetime
    payload_hash: str | None = None
    signature_status: str
    generated_by: str | None = None
    invalidated_at: datetime | None = None
    invalidation_reason: str | None = None
    replaced_by_label_id: str | None = None
    replaced_at: datetime | None = None


class AisleLocationLabelListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AisleLocationLabelResponse]


def aisle_location_to_response(location: AisleLocation) -> AisleLocationResponse:
    return AisleLocationResponse(
        id=location.id,
        client_id=location.client_id,
        aisle_id=location.aisle_id,
        code=location.code,
        normalized_code=location.normalized_code,
        status=location.status.value,
        created_at=location.created_at,
        updated_at=location.updated_at,
        display_name=location.display_name,
        description=location.description,
        created_by=location.created_by,
        public_identifier=location.public_identifier or "",
    )


def aisle_location_label_to_response(label: AisleLocationLabel) -> AisleLocationLabelResponse:
    return AisleLocationLabelResponse(
        id=label.id,
        client_id=label.client_id,
        location_id=label.location_id,
        public_identifier=label.public_identifier,
        payload_version=label.payload_version,
        marker_version=label.marker_version,
        template_version=label.template_version,
        status=label.status.value,
        payload=label.payload,
        generated_at=label.generated_at,
        payload_hash=label.payload_hash,
        signature_status=label.signature_status.value,
        generated_by=label.generated_by,
        invalidated_at=label.invalidated_at,
        invalidation_reason=label.invalidation_reason,
        replaced_by_label_id=label.replaced_by_label_id,
        replaced_at=label.replaced_at,
    )


def aisle_location_label_artifact_to_response(artifact) -> AisleLocationLabelArtifactResponse:
    return AisleLocationLabelArtifactResponse(
        id=artifact.id,
        label_id=artifact.label_id,
        format=artifact.format,
        preset=artifact.preset,
        template_version=int(artifact.template_version),
        marker_version=int(artifact.marker_version),
        content_type=artifact.content_type,
        file_size_bytes=int(artifact.file_size_bytes),
        artifact_hash=artifact.artifact_hash,
        created_at=artifact.created_at,
    )
