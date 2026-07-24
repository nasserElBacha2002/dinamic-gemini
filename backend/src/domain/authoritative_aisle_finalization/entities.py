"""Authoritative aisle finalization domain types (Phase 6)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class AuthoritativeFinalizationStatus(str, Enum):
    FINALIZING = "FINALIZING"
    COMPLETED_BY_LOCAL_AUTHORITY = "COMPLETED_BY_LOCAL_AUTHORITY"
    FINALIZATION_FAILED = "FINALIZATION_FAILED"
    CANCELED = "CANCELED"


class AuthoritativeFinalizationItemStatus(str, Enum):
    CONFIRMED_AND_APPLIED = "CONFIRMED_AND_APPLIED"
    EXCLUDED = "EXCLUDED"


class AuthoritativeExclusionReason(str, Enum):
    DUPLICATE_PHOTO = "DUPLICATE_PHOTO"
    INVALID_PHOTO = "INVALID_PHOTO"
    NOT_INVENTORY_LABEL = "NOT_INVENTORY_LABEL"
    USER_EXCLUDED = "USER_EXCLUDED"
    CAPTURE_ERROR = "CAPTURE_ERROR"


class AuthoritativeAisleReadinessStatus(str, Enum):
    READY = "READY"
    NOT_READY = "NOT_READY"
    BLOCKED = "BLOCKED"


class AuthoritativeReadinessReason(str, Enum):
    PENDING_LOCAL_SCAN = "PENDING_LOCAL_SCAN"
    PENDING_LOCAL_REVIEW = "PENDING_LOCAL_REVIEW"
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
    PENDING_UPLOAD = "PENDING_UPLOAD"
    PENDING_AUTHORITATIVE_SYNC = "PENDING_AUTHORITATIVE_SYNC"
    PENDING_FINAL_APPLY = "PENDING_FINAL_APPLY"
    AUTHORITATIVE_CONFLICT = "AUTHORITATIVE_CONFLICT"
    AUTHORITATIVE_REJECTED = "AUTHORITATIVE_REJECTED"
    AUTHORITATIVE_FAILED_TERMINAL = "AUTHORITATIVE_FAILED_TERMINAL"
    PHOTO_NOT_DECIDED = "PHOTO_NOT_DECIDED"
    ASSET_MISSING = "ASSET_MISSING"
    POSITION_MISSING = "POSITION_MISSING"
    DUPLICATE_CURRENT_POSITION = "DUPLICATE_CURRENT_POSITION"
    SESSION_INCONSISTENT = "SESSION_INCONSISTENT"
    FEATURE_DISABLED = "FEATURE_DISABLED"
    AISLE_ALREADY_FINALIZED = "AISLE_ALREADY_FINALIZED"


@dataclass(frozen=True)
class AuthoritativeAisleFinalization:
    id: str
    inventory_id: str
    aisle_id: str
    capture_session_id: str | None
    finalization_version: int
    status: str
    total_assets: int
    applied_assets: int
    excluded_assets: int
    position_count: int
    expected_asset_count: int | None
    content_hash: str
    confirmed_by: str
    confirmed_at: datetime
    completed_at: datetime | None
    is_current: bool
    row_version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class AuthoritativeAisleFinalizationItem:
    id: str
    finalization_id: str
    asset_id: str
    authoritative_result_id: str | None
    position_id: str | None
    item_status: str
    created_at: datetime


@dataclass(frozen=True)
class AuthoritativeAisleExcludedAsset:
    id: str
    inventory_id: str
    aisle_id: str
    asset_id: str
    reason: str
    excluded_by: str
    excluded_at: datetime
    is_current: bool
    created_at: datetime
    updated_at: datetime
