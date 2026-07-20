"""Auditable processing attempt for job_id + asset_id + strategy (Phase 2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ProcessingAttemptStatus(str, Enum):
    STARTED = "STARTED"
    SUCCEEDED = "SUCCEEDED"
    INVALID = "INVALID"
    UNRECOGNIZED = "UNRECOGNIZED"
    FAILED_TECHNICAL = "FAILED_TECHNICAL"
    CANCELLED = "CANCELLED"


@dataclass
class ProcessingAttempt:
    id: str
    job_id: str
    asset_id: str
    strategy: str
    attempt_number: int
    status: ProcessingAttemptStatus
    created_at: datetime
    provider: str | None = None
    model: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    raw_result_reference: str | None = None
    normalized_result: dict[str, Any] | None = None
    validation_result: dict[str, Any] | None = None
    execution_scope: str | None = None
    logical_asset_attempt: bool = True
    configuration_snapshot_version: int | None = None
    parent_batch_attempt_id: str | None = None
    batch_execution_id: str | None = None
    worker_token: str | None = None
    updated_at: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)
