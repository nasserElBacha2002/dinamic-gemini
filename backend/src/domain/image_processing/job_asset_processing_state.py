"""Persisted per-asset processing state for a job (Phase 2)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class JobAssetProcessingStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    RESOLVED = "RESOLVED"
    UNRECOGNIZED = "UNRECOGNIZED"
    FAILED_TECHNICAL = "FAILED_TECHNICAL"
    PENDING_MANUAL_REVIEW = "PENDING_MANUAL_REVIEW"
    CANCELLED = "CANCELLED"


@dataclass
class JobAssetProcessingState:
    id: str
    job_id: str
    asset_id: str
    status: JobAssetProcessingStatus
    created_at: datetime
    updated_at: datetime
    active_result_id: str | None = None
    attempt_count: int = 0
    last_strategy: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    version: int = 1
    execution_scope: str | None = None
    worker_token: str | None = None
    lease_expires_at: datetime | None = None
