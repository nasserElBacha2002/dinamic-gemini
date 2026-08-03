"""Manual product-position override domain model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class PositionOverrideAction(str, Enum):
    ASSIGN_POSITION = "ASSIGN_POSITION"
    CHANGE_POSITION = "CHANGE_POSITION"
    REMOVE_POSITION = "REMOVE_POSITION"
    RESTORE_AUTOMATIC = "RESTORE_AUTOMATIC"


class PositionOverrideReasonCode(str, Enum):
    WRONG_POSITION_DETECTED = "WRONG_POSITION_DETECTED"
    PRODUCT_MOVED = "PRODUCT_MOVED"
    SEQUENCE_ERROR = "SEQUENCE_ERROR"
    POSITION_LABEL_NOT_VISIBLE = "POSITION_LABEL_NOT_VISIBLE"
    POSITION_LABEL_INVALID = "POSITION_LABEL_INVALID"
    AMBIGUOUS_IMAGE = "AMBIGUOUS_IMAGE"
    MISSING_POSITION_LABEL = "MISSING_POSITION_LABEL"
    OPERATOR_VERIFICATION = "OPERATOR_VERIFICATION"
    DATA_CORRECTION = "DATA_CORRECTION"
    OTHER = "OTHER"


class EffectivePositionSource(str, Enum):
    AUTOMATIC = "AUTOMATIC"
    MANUAL = "MANUAL"
    NONE = "NONE"


@dataclass(frozen=True)
class PositionOverridePositionRef:
    id: str | None
    name: str | None


@dataclass(frozen=True)
class ManualProductPositionOverride:
    id: str
    client_id: str
    inventory_id: str
    aisle_id: str
    job_id: str
    result_id: str
    source_asset_id: str | None
    automatic_assignment_id: str | None
    automatic_reconciliation_id: str | None
    previous_effective_position_label_id: str | None
    new_position_label_id: str | None
    new_position_name_snapshot: str | None
    override_action: PositionOverrideAction
    reason_code: PositionOverrideReasonCode
    reason_text: str | None
    created_by_user_id: str
    created_by_role: str
    idempotency_key: str
    version: int
    is_active: bool
    superseded_override_id: str | None
    created_at: datetime
    updated_at: datetime
    deactivated_at: datetime | None = None


@dataclass(frozen=True)
class EffectiveProductPositionView:
    result_id: str
    effective_position: PositionOverridePositionRef | None
    effective_source: EffectivePositionSource
    effective_status: str
    automatic_position: PositionOverridePositionRef | None
    automatic_assignment_status: str | None
    manual_override: ManualProductPositionOverride | None
    reconciliation_status: str | None
    warnings: tuple[str, ...]
    version: int
    automatic_reconciliation_id: str | None = None
    automatic_assignment_id: str | None = None
    source_asset_id: str | None = None
