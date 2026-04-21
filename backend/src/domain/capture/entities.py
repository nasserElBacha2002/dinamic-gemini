"""
Capture session aggregate — Sprint 1 domain model.

Session/item states are application-enforced strings persisted as VARCHAR; enums document
allowed values. Invalid transitions are rejected in future use cases (not in entity methods
for Sprint 1 beyond basic documentation here).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class CaptureSessionStatus(str, Enum):
    """Lifecycle for a capture session (wire / DB value = enum value)."""

    DRAFT = "draft"
    IMPORTING = "importing"
    READY_FOR_REVIEW = "ready_for_review"
    ASSIGNMENT_PROPOSED = "assignment_proposed"
    CONFIRMING = "confirming"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class CaptureSessionItemImportStatus(str, Enum):
    PENDING_IMPORT = "pending_import"
    IMPORTING = "importing"
    IMPORTED = "imported"
    IMPORT_FAILED = "import_failed"


class CaptureTimeSource(str, Enum):
    EXIF = "exif"
    FILE_MTIME = "file_mtime"
    FALLBACK_CLOCK = "fallback_clock"


class CaptureSessionItemAssignmentStatus(str, Enum):
    """Preview / assignment outcome (Sprint 3+); ``pending`` until preview runs."""

    PENDING = "pending"
    PROPOSED = "proposed"
    CONFLICT = "conflict"
    UNASSIGNED = "unassigned"


@dataclass
class CaptureSession:
    id: str
    inventory_id: str
    aisle_id: str
    status: CaptureSessionStatus
    created_at: datetime
    updated_at: datetime
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None


@dataclass
class CaptureSessionItem:
    id: str
    session_id: str
    staging_storage_key: str
    import_status: CaptureSessionItemImportStatus
    assignment_status: CaptureSessionItemAssignmentStatus
    updated_at: datetime
    content_hash: Optional[str] = None
    effective_capture_time: Optional[datetime] = None
    time_source: Optional[CaptureTimeSource] = None
    time_confidence: Optional[float] = None
    linked_source_asset_id: Optional[str] = None
    last_error_code: Optional[str] = None
    last_error_detail: Optional[str] = None
    original_filename: Optional[str] = None


@dataclass
class CaptureSessionConfirmationLedgerEntry:
    """Persisted idempotency record for confirm-session (Sprint 6+)."""

    id: str
    session_id: str
    idempotency_key: str
    created_at: datetime
    outcome_json: Optional[Dict[str, Any]] = None
