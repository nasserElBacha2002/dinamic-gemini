"""API schemas for job image coverage (photos LEFT JOIN positions)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.api.schemas.listing_schemas import PageMeta
from src.api.schemas.position_schemas import PositionSummaryResponse

ResultStatusQuery = Literal["all", "with_result", "without_result"]


class JobImageResultCountersResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_images: int
    with_result: int
    without_result: int


class JobImageResultItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_id: str
    source_asset_id: str
    job_id: str
    image_url: str
    original_filename: str | None = None
    created_at: datetime
    processing_status: str | None = None
    has_result: bool
    result_count: int
    results: list[PositionSummaryResponse]


class JobImageResultsResponse(PageMeta):
    """GET …/jobs/{job_id}/image-results — paginated by image, not by position."""

    model_config = ConfigDict(extra="ignore")

    items: list[JobImageResultItemResponse]
    counters: JobImageResultCountersResponse


class CreateManualImageResultRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(..., min_length=1)
    sku: str = Field(..., min_length=1)
    quantity: int = Field(..., ge=0)
    description: str | None = None
    position_code: str | None = None


class CreateManualImageResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: PositionSummaryResponse
