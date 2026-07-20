from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CreateSupplierExtractionProfileRequest(BaseModel):
    configuration: dict[str, Any] | None = None
    visual_notes: str | None = None
    profile_key: str | None = None
    activate: bool = False


class ActivateSupplierExtractionProfileRequest(BaseModel):
    expected_row_version: int | None = None


class CloneSupplierExtractionProfileRequest(BaseModel):
    source_profile_id: str


class TestExtractionProfileRequest(BaseModel):
    """Diagnostic dry-run — does not create positions or mutate inventory."""

    configuration: dict[str, Any]
    image_base64: str = Field(..., min_length=8, max_length=12_000_000)


class TestExtractionProfileResponse(BaseModel):
    client_id: str
    supplier_id: str
    label_detected: bool
    selected_relative_area: float | None = None
    matched_anchors: list[str] = Field(default_factory=list)
    candidate_count: int = 0
    geometry: dict[str, Any] = Field(default_factory=dict)
    ocr: dict[str, Any] = Field(default_factory=dict)
    code_candidate: str | None = None
    quantity_candidate: float | int | None = None
    rejected_candidates: list[dict[str, Any]] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    expected_status: str
    error_code: str | None = None
    profile_rules_applied: dict[str, Any] = Field(default_factory=dict)
    persists_inventory: bool = False


class SupplierExtractionProfileResponse(BaseModel):
    id: str
    client_id: str
    supplier_id: str
    profile_key: str
    version: int
    status: str
    configuration: dict[str, Any]
    visual_notes: str | None
    created_by: str | None
    created_at: datetime
    activated_by: str | None = None
    activated_at: datetime | None = None
    superseded_at: datetime | None = None
    updated_at: datetime | None = None
    row_version: int


class SupplierExtractionProfilesListResponse(BaseModel):
    items: list[SupplierExtractionProfileResponse]


class ReferenceAnnotationPayload(BaseModel):
    id: str | None = None
    field_key: str
    anchor_texts: list[str] = Field(default_factory=list)
    spatial_relation: str
    normalized_polygon: list[list[float]] | None = None
    priority: int = 1
    required: bool = False
    max_distance_ratio: float | None = None


class ReplaceSupplierReferenceAnnotationsRequest(BaseModel):
    profile_id: str | None = None
    annotations: list[ReferenceAnnotationPayload] = Field(default_factory=list)


class ReferenceAnnotationResponse(BaseModel):
    id: str
    template_image_id: str
    profile_id: str | None
    field_key: str
    anchor_texts: list[str]
    spatial_relation: str
    normalized_polygon: list[list[float]] | None = None
    priority: int
    required: bool
    max_distance_ratio: float | None = None


class SupplierReferenceAnnotationsListResponse(BaseModel):
    items: list[ReferenceAnnotationResponse]
