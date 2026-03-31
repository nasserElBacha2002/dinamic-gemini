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
    STARTING = "starting"
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
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    last_heartbeat_at: Optional[datetime] = None
    cancel_requested_at: Optional[datetime] = None
    current_stage: Optional[str] = None
    current_substep: Optional[str] = None
    current_step_started_at: Optional[datetime] = None
    attempt_count: int = 1
    retry_of_job_id: Optional[str] = None
    failure_code: Optional[str] = None
    failure_message: Optional[str] = None
    execution_id: Optional[str] = None
