"""Code scan domain entities — aisle QR/barcode auxiliary flow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class CodeScanRunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"


class CodeScanDetectionStatus(str, Enum):
    DETECTED = "detected"
    DUPLICATE = "duplicate"
    LOW_CONFIDENCE = "low_confidence"
    ERROR = "error"


class CodeType(str, Enum):
    QR = "qr"
    BARCODE = "barcode"
    DATAMATRIX = "datamatrix"
    UNKNOWN = "unknown"


@dataclass
class CodeScanRun:
    id: str
    inventory_id: str
    aisle_id: str
    status: CodeScanRunStatus
    total_assets: int
    processed_assets: int
    failed_assets: int
    total_codes_found: int
    total_qr_found: int
    total_barcodes_found: int
    started_at: datetime
    finished_at: datetime | None
    scanner_engine: str
    is_latest: bool
    error_message: str | None = None
    created_by: str | None = None
    metadata_json: dict[str, Any] | None = None


@dataclass
class CodeScanDetection:
    id: str
    run_id: str
    inventory_id: str
    aisle_id: str
    asset_id: str
    code_type: CodeType
    code_value: str
    normalized_code_value: str
    detection_status: CodeScanDetectionStatus
    scanner_engine: str
    created_at: datetime
    #: Stable object contract — see ``domain.code_scans.bounding_box`` (rect + unit + x/y/width/height).
    bounding_box_json: dict[str, Any] | None = None
    confidence: float | None = None
    metadata_json: dict[str, Any] | None = None
    #: Phase 4 read-only match snapshot (nullable until matching runs).
    matched_position_id: str | None = None
    match_status: str | None = None
    match_type: str | None = None
    match_confidence: float | None = None
    match_metadata_json: dict[str, Any] | None = None
    matched_at: datetime | None = None
