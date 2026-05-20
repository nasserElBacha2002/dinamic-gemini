"""v3 aisle code scan API schemas — Phase 1 backend foundation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class CodeScanBoundingBoxRectResponse(BaseModel):
    x: float
    y: float
    width: float
    height: float


class CodeScanBoundingBoxResponse(BaseModel):
    """Stable bounding box persisted in ``bounding_box_json`` (rect or rect_polygon)."""

    format: Literal["rect", "rect_polygon"]
    unit: Literal["pixel", "normalized"]
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None
    rect: CodeScanBoundingBoxRectResponse | None = None
    polygon: list[list[float]] | None = None


class CodeScanRunSummaryResponse(BaseModel):
    id: str
    status: str
    total_assets: int
    processed_assets: int
    failed_assets: int
    total_codes_found: int
    total_qr_found: int
    total_barcodes_found: int
    started_at: datetime
    finished_at: datetime | None = None
    scanner_engine: str
    error_message: str | None = None
    warnings: list[str] = Field(default_factory=list)


class RunAisleCodeScanResponse(BaseModel):
    run: CodeScanRunSummaryResponse


class CodeScanDetectionResponse(BaseModel):
    id: str
    run_id: str
    asset_id: str
    code_type: str
    code_value: str
    normalized_code_value: str
    detection_status: str
    confidence: float | None = None
    bounding_box_json: CodeScanBoundingBoxResponse | None = None
    scanner_engine: str
    created_at: datetime
    metadata_json: dict[str, Any] | None = None
    matched_position_id: str | None = None
    match_status: str | None = None
    match_type: str | None = None
    match_confidence: float | None = None
    match_metadata_json: dict[str, Any] | None = None
    matched_at: datetime | None = None


class ListAisleCodeScansResponse(BaseModel):
    latest_run: CodeScanRunSummaryResponse | None = None
    detections: list[CodeScanDetectionResponse] = Field(default_factory=list)


class CodeScanSummaryItemResponse(BaseModel):
    code_value: str
    normalized_code_value: str
    code_type: str
    occurrences: int
    asset_ids: list[str]
    first_seen_at: datetime
    match_status: str | None = None
    matched_position_ids: list[str] = Field(default_factory=list)
    match_types: list[str] = Field(default_factory=list)
    match_status_counts: dict[str, int] | None = None


class SummarizeAisleCodeScansResponse(BaseModel):
    latest_run: CodeScanRunSummaryResponse | None = None
    items: list[CodeScanSummaryItemResponse] = Field(default_factory=list)
