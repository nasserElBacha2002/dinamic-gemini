"""v3.0 Processing API schemas (process, status)."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from src.api.schemas.aisle_schemas import AisleResponse
from src.api.schemas.reference_usage_schemas import ReferenceUsageSummary


class ProcessAisleRequest(BaseModel):
    """Optional body for POST .../aisles/{aisle_id}/process (Phase 5)."""

    provider_name: Optional[str] = Field(
        None,
        description=(
            "Pipeline provider key (gemini, fake, openai). Omit or null to use the server default "
            "(settings.llm_provider) without proactive credential validation."
        ),
    )


class ProcessingProviderOptionItem(BaseModel):
    key: str
    label: str
    execution_mode: str = Field(
        ...,
        description="native | transitional_bridge — informational for UI; both are real execution paths.",
    )
    description: Optional[str] = None


class ProcessingProviderOptionsResponse(BaseModel):
    """GET /api/v3/inventories/processing-provider-options — keys the client may send as provider_name."""

    default_provider_key: str
    providers: List[ProcessingProviderOptionItem] = Field(default_factory=list)


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
    retry_of_job_id: Optional[str] = None
    failure_code: Optional[str] = None
    failure_message: Optional[str] = None
    execution_id: Optional[str] = None
    provider_name: Optional[str] = None
    model_name: Optional[str] = None
    prompt_key: Optional[str] = None


class AisleStatusResponse(BaseModel):
    """Response for GET .../aisles/{aisle_id}/status."""
    aisle: AisleResponse
    latest_job: Optional[JobSummary] = None
    operational_job_id: Optional[str] = None
    recent_jobs: List[JobSummary] = Field(default_factory=list)


class AisleJobsListResponse(BaseModel):
    """Response for GET .../aisles/{aisle_id}/jobs (Phase 2 run browser)."""
    operational_job_id: Optional[str] = None
    jobs: List[JobSummary] = Field(default_factory=list)


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

