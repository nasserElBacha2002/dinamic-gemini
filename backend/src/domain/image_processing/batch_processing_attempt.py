"""Auditable physical execution attempt for one AISLE_BATCH run (Phase 2 corrections).

Distinct from ``ProcessingAttempt`` (logical, per-asset bookkeeping): one
``BatchProcessingAttempt`` row corresponds to one physical legacy batch runner invocation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class BatchProcessingAttemptStatus(str, Enum):
    STARTED = "STARTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED_TECHNICAL = "FAILED_TECHNICAL"
    CANCELLED = "CANCELLED"


@dataclass
class BatchProcessingAttempt:
    id: str
    job_id: str
    strategy: str
    execution_scope: str
    status: BatchProcessingAttemptStatus
    created_at: datetime
    updated_at: datetime
    provider: str | None = None
    model: str | None = None
    prompt_key: str | None = None
    prompt_version: str | None = None
    worker_token: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None
