"""v3 aisle code scan API schemas — Phase 1 backend foundation."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


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
    bounding_box_json: list[float] | None = None
    scanner_engine: str
    created_at: datetime
    metadata_json: dict[str, Any] | None = None


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


class SummarizeAisleCodeScansResponse(BaseModel):
    latest_run: CodeScanRunSummaryResponse | None = None
    items: list[CodeScanSummaryItemResponse] = Field(default_factory=list)
