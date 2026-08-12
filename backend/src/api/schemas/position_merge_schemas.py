"""Schemas for operator-driven position merge (preview + confirm)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PositionMergeRequest(BaseModel):
    result_ids: list[str] = Field(..., min_length=1)


class PositionMergeConfirmRequest(BaseModel):
    result_ids: list[str] = Field(..., min_length=1)
    preview_token: str = Field(..., min_length=1)


class PositionMergeConflictDto(BaseModel):
    code: str
    message: str
    values: list[str] = Field(default_factory=list)


class PositionMergeWarningDto(BaseModel):
    code: str
    message: str
    values: list[str] = Field(default_factory=list)


class PositionMergeSourceDto(BaseModel):
    position_id: str
    sku: str | None = None
    internal_code: str | None = None
    barcode: str | None = None
    description: str | None = None
    quantity: int
    position_code: str | None = None
    source_image_id: str | None = None
    source_image_filename: str | None = None
    job_id: str | None = None
    confidence: float | None = None
    status: str | None = None
    review_resolution: str | None = None


class PositionMergeProposedResultDto(BaseModel):
    survivor_id: str | None = None
    sku: str | None = None
    internal_code: str | None = None
    description: str | None = None
    quantity: int | None = None
    position_code: str | None = None
    source_count: int = 0
    image_count: int = 0
    product_identity: str | None = None


class PositionMergePreviewResponse(BaseModel):
    can_merge: bool
    preview_token: str
    sources: list[PositionMergeSourceDto]
    merged_result: PositionMergeProposedResultDto
    warnings: list[PositionMergeWarningDto] = Field(default_factory=list)
    conflicts: list[PositionMergeConflictDto] = Field(default_factory=list)


class PositionMergeConfirmResponse(BaseModel):
    survivor_id: str
    merged_quantity: int
    source_ids: list[str]
    already_merged: bool = False
