"""
Job domain entity — v3.0 (Documento técnico §7.8).

Technical work item associated with an aisle. Distinct from src/jobs (queue/store implementation).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    # Cancellation-related states — Stage 6:
    # - CANCEL_REQUESTED: operator requested cancellation; job may still be running.
    # - CANCELED: job observed cancellation and stopped cooperatively (no final report).
    # - TIMED_OUT: reserved for future timeout handling (not used in v3.1.2 Stage 6).
    CANCEL_REQUESTED = "cancel_requested"
    CANCELED = "canceled"
    TIMED_OUT = "timed_out"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class Job:
    id: str
    target_type: str
    target_id: str
    job_type: str
    status: JobStatus
    payload_json: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    result_json: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
