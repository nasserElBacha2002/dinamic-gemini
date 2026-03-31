"""v3.0 Processing API schemas (process, status)."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from src.api.schemas.aisle_schemas import AisleResponse
from src.api.schemas.reference_usage_schemas import ReferenceUsageSummary


class ProcessAisleResponse(BaseModel):
    """Response for POST .../aisles/{aisle_id}/process."""
    job_id: str


class JobSummary(BaseModel):
    """Summary of latest job for an aisle."""
    id: str
    status: str
    created_at: datetime
    updated_at: datetime
    error_message: Optional[str] = None
    reference_usage: Optional[ReferenceUsageSummary] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    last_heartbeat_at: Optional[datetime] = None
    cancel_requested_at: Optional[datetime] = None
    current_stage: Optional[str] = None
    current_substep: Optional[str] = None
    current_step_started_at: Optional[datetime] = None
    attempt_count: int = 1
    failure_code: Optional[str] = None
    failure_message: Optional[str] = None
    execution_id: Optional[str] = None


class AisleStatusResponse(BaseModel):
    """Response for GET .../aisles/{aisle_id}/status."""
    aisle: AisleResponse
    latest_job: Optional[JobSummary] = None


class ExecutionLogEvent(BaseModel):
    """Single entry in the job execution log (v3.1.1)."""
    ts: str
    stage: str
    level: str
    message: str
    payload: Optional[Dict[str, Any]] = None


class ExecutionLogResponse(BaseModel):
    """Response for GET .../aisles/{aisle_id}/jobs/{job_id}/execution-log."""
    events: List[ExecutionLogEvent]

