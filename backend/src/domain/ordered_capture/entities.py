"""Ordered capture session — Phase 1 positioning foundation.

Distinct from web ingestion ``capture_sessions``: this entity is the mobile/drone
spine that carries explicit ``sequence_number`` assignment and seal-before-process.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class OrderedCaptureSessionStatus(str, Enum):
    OPEN = "OPEN"
    UPLOADING = "UPLOADING"
    SEALED = "SEALED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class SequenceSource(str, Enum):
    """How ``sequence_number`` on a source asset was obtained."""

    CLIENT_ASSIGNED = "CLIENT_ASSIGNED"
    LEGACY_DERIVED = "LEGACY_DERIVED"


@dataclass
class OrderedCaptureSession:
    id: str
    inventory_id: str
    aisle_id: str
    status: OrderedCaptureSessionStatus
    created_at: datetime
    updated_at: datetime
    client_id: str | None = None
    expected_asset_count: int | None = None
    uploaded_asset_count: int = 0
    sequence_version: int = 1
    created_by: str | None = None
    sealed_at: datetime | None = None
    processing_started_at: datetime | None = None
    processing_job_id: str | None = None
    completed_at: datetime | None = None
