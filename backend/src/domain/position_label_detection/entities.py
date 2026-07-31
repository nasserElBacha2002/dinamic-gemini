"""Image-level position label detections (Phase 3) — no product↔position binding."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class PositionLabelDetectionStatus(str, Enum):
    """Structured validation / resolution outcomes for one detection row."""

    VALID = "VALID"
    INVALID_JSON = "INVALID_JSON"
    INVALID_TYPE = "INVALID_TYPE"
    UNSUPPORTED_VERSION = "UNSUPPORTED_VERSION"
    UNSUPPORTED_LEGACY_PAYLOAD = "UNSUPPORTED_LEGACY_PAYLOAD"
    MISSING_LABEL_ID = "MISSING_LABEL_ID"
    MISSING_SIGNATURE = "MISSING_SIGNATURE"
    INVALID_SIGNATURE = "INVALID_SIGNATURE"
    UNKNOWN_KEY_VERSION = "UNKNOWN_KEY_VERSION"
    LABEL_NOT_FOUND = "LABEL_NOT_FOUND"
    LABEL_INVALIDATED = "LABEL_INVALIDATED"
    CLIENT_MISMATCH = "CLIENT_MISMATCH"
    DUPLICATE_POSITION_CODES = "DUPLICATE_POSITION_CODES"
    AMBIGUOUS_POSITION_DETECTION = "AMBIGUOUS_POSITION_DETECTION"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    DECODE_TIMEOUT = "DECODE_TIMEOUT"
    DETECTION_FAILED = "DETECTION_FAILED"
    NO_LABEL = "NO_LABEL"
    FEATURE_DISABLED = "FEATURE_DISABLED"


class PositionLabelSignatureStatus(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    MISSING = "MISSING"
    SKIPPED = "SKIPPED"
    UNKNOWN_KEY = "UNKNOWN_KEY"


class ImageCodeKind(str, Enum):
    POSITION = "POSITION"
    ITEM = "ITEM"
    UNKNOWN = "UNKNOWN"


DETECTOR_NAME = "code_scan_shared"
DETECTOR_VERSION = "position-label-detection-1.0.0"


@dataclass(frozen=True)
class DetectedCode:
    """Generic decoded symbol — no DB / tenant decisions."""

    symbology: str
    raw_value: str
    normalized_value: str
    bounding_box: dict[str, Any] | None = None
    confidence: float | None = None
    rotation_degrees: float | None = None


@dataclass
class ImagePositionLabelDetection:
    id: str
    client_id: str
    inventory_id: str
    job_id: str
    source_asset_id: str
    detection_status: PositionLabelDetectionStatus
    signature_status: PositionLabelSignatureStatus
    payload_version: int | None
    raw_payload_hash: str | None
    detector_name: str
    detector_version: str
    created_at: datetime
    updated_at: datetime
    client_image_id: str | None = None
    ordered_capture_session_id: str | None = None
    sequence_number: int | None = None
    position_label_id: str | None = None
    public_identifier: str | None = None
    position_name_snapshot: str | None = None
    confidence: float | None = None
    bounding_box_json: dict[str, Any] | None = None
    rotation_degrees: float | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)
