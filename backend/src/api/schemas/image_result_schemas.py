"""API schemas for job image coverage (photos LEFT JOIN positions)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.api.schemas.listing_schemas import PageMeta
from src.api.schemas.position_schemas import PositionSummaryResponse
from src.application.services.manual_image_result_input import (
    DESCRIPTION_MAX_LENGTH,
    POSITION_CODE_MAX_LENGTH,
    SKU_MAX_LENGTH,
)

ResultStatusQuery = Literal["all", "with_result", "without_result"]


class JobImageResultCountersResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_images: int
    with_result: int
    without_result: int


class JobImageResultItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_source_asset_id: str
    source_asset_id: str
    job_id: str
    image_url: str
    original_filename: str | None = None
    created_at: datetime
    position_order: int
    processing_status: str | None = None
    has_result: bool
    result_count: int
    automatic_result_count: int
    manual_result_count: int
    has_manual_result: bool
    results: list[PositionSummaryResponse]


class JobImageResultsResponse(PageMeta):
    """GET …/jobs/{job_id}/image-results — paginated by image, not by position."""

    model_config = ConfigDict(extra="forbid")

    items: list[JobImageResultItemResponse]
    counters: JobImageResultCountersResponse


class CreateManualImageResultRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(..., min_length=1)
    sku: str = Field(..., min_length=1, max_length=SKU_MAX_LENGTH)
    quantity: int = Field(..., gt=0)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    position_code: str | None = Field(default=None, max_length=POSITION_CODE_MAX_LENGTH)


class CreateManualImageResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: PositionSummaryResponse
