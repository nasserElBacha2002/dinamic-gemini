"""Per (job, strategy, execution_scope) exclusive lease for batch processing (Phase 2 corrections).

Prevents two concurrent workers from re-running the same legacy AISLE_BATCH call for the
same job. One row per ``UNIQUE(job_id, strategy, execution_scope)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class JobProcessingLeaseStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    ACQUIRED = "ACQUIRED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class JobProcessingLease:
    id: str
    job_id: str
    strategy: str
    execution_scope: str
    status: JobProcessingLeaseStatus
    created_at: datetime
    updated_at: datetime
    worker_token: str | None = None
    acquired_at: datetime | None = None
    heartbeat_at: datetime | None = None
    lease_expires_at: datetime | None = None
    released_at: datetime | None = None
    version: int = 1
