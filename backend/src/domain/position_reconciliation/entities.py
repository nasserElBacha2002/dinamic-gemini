"""Domain contracts for sequential product-to-position reconciliation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from src.domain.position_label_detection.entities import (
    PositionLabelDetectionStatus,
    PositionLabelSignatureStatus,
)

RECONCILIATION_NAME = "sequential-last-valid-position"
RECONCILIATION_VERSION = "1.0.0"


class AssignmentStatus(str, Enum):
    ASSIGNED_AUTOMATIC = "ASSIGNED_AUTOMATIC"
    UNASSIGNED_NO_PREVIOUS_POSITION = "UNASSIGNED_NO_PREVIOUS_POSITION"
    UNASSIGNED_AFTER_AMBIGUOUS_POSITION = "UNASSIGNED_AFTER_AMBIGUOUS_POSITION"
    UNASSIGNED_INVALID_POSITION = "UNASSIGNED_INVALID_POSITION"
    UNASSIGNED_UNORDERED_ASSET = "UNASSIGNED_UNORDERED_ASSET"
    SKIPPED_NO_ITEM_RESULT = "SKIPPED_NO_ITEM_RESULT"


class ReconciliationStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    STALE = "STALE"


class PositionTransitionAction(str, Enum):
    SET_POSITION = "SET_POSITION"
    KEEP_POSITION = "KEEP_POSITION"
    CLEAR_POSITION = "CLEAR_POSITION"


class AssignmentSource(str, Enum):
    AUTOMATIC = "AUTOMATIC"


@dataclass(frozen=True)
class ItemResultRef:
    result_id: str


@dataclass(frozen=True)
class PositionDetectionRef:
    id: str
    client_id: str
    detection_status: PositionLabelDetectionStatus | str
    signature_status: PositionLabelSignatureStatus | str
    position_label_id: str | None = None
    position_name_snapshot: str | None = None
    detector_version: str | None = None


@dataclass(frozen=True)
class OrderedImageFrame:
    source_asset_id: str
    ordered_capture_session_id: str | None
    sequence_number: int | None
    item_results: tuple[ItemResultRef, ...] = ()
    position_detections: tuple[PositionDetectionRef, ...] = ()
    client_image_id: str | None = None


@dataclass(frozen=True)
class PositionAssignmentDecision:
    result_id: str
    source_asset_id: str
    ordered_capture_session_id: str | None
    sequence_number: int | None
    assignment_status: AssignmentStatus
    assignment_reason: str
    position_label_id: str | None = None
    position_name_snapshot: str | None = None
    source_detection_id: str | None = None
    assignment_source: AssignmentSource | None = None
    warnings: tuple[str, ...] = ()


@dataclass
class PositionReconciliation:
    id: str
    client_id: str
    inventory_id: str
    job_id: str
    ordered_capture_session_id: str | None
    input_fingerprint: str
    status: ReconciliationStatus
    started_at: datetime
    created_at: datetime
    updated_at: datetime
    reconciliation_name: str = RECONCILIATION_NAME
    reconciliation_version: str = RECONCILIATION_VERSION
    completed_at: datetime | None = None
    failure_code: str | None = None
    attempt_count: int = 1
    assigned_count: int = 0
    unassigned_count: int = 0
    sequence_gap_count: int = 0
    metadata_json: dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
    superseded_at: datetime | None = None


@dataclass
class ProductPositionAssignment:
    id: str
    client_id: str
    inventory_id: str
    job_id: str
    result_id: str
    source_asset_id: str
    ordered_capture_session_id: str | None
    sequence_number: int | None
    assignment_status: AssignmentStatus
    assignment_reason: str
    reconciliation_id: str
    reconciliation_version: str
    created_at: datetime
    updated_at: datetime
    position_label_id: str | None = None
    position_name_snapshot: str | None = None
    source_detection_id: str | None = None
    assignment_source: AssignmentSource | None = None
    is_active: bool = True
    superseded_at: datetime | None = None
