"""v3.0 Processing API schemas (process, status)."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from src.api.schemas.aisle_schemas import AisleResponse
from src.api.schemas.reference_usage_schemas import ReferenceUsageSummary


class ProcessAisleRequest(BaseModel):
    """Optional body for POST .../aisles/{aisle_id}/process (Phase 5)."""

    provider_name: Optional[str] = Field(
        None,
        description=(
            "Pipeline provider key (gemini, openai, claude, deepseek). Omit or null to use the server default "
            "(settings.llm_provider) without proactive credential validation."
        ),
    )
    model_name: Optional[str] = Field(
        None,
        description="Model id from processing-provider-options for the selected provider; omit for provider default.",
    )
    prompt_key: Optional[str] = Field(
        None,
        description="Hybrid prompt profile key (e.g. global_v21, global_v21_b); omit for HYBRID_PROMPT default.",
    )


class ProcessingModelOption(BaseModel):
    id: str
    label: str


class ProcessingPromptOptionItem(BaseModel):
    key: str
    label: str
    description: Optional[str] = None


class ProcessingProviderOptionItem(BaseModel):
    key: str
    label: str
    execution_mode: str = Field(
        ...,
        description="native — pipeline providers use native SDK executors.",
    )
    description: Optional[str] = None
    models: List[ProcessingModelOption] = Field(default_factory=list)
    default_model: Optional[str] = Field(
        None, description="Default model id for this provider when model_name is omitted."
    )


class ProcessingProviderOptionsResponse(BaseModel):
    """GET /api/v3/inventories/processing-provider-options — discovery for POST process."""

    default_provider_key: str
    default_prompt_key: str
    prompt_profiles: List[ProcessingPromptOptionItem] = Field(default_factory=list)
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
    prompt_version: Optional[str] = None
    #: True when this job is the aisle ``operational_job_id`` pointer (Phase 6 run browser).
    is_operational: bool = False


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
    """Single execution log row with raw fields plus derived filter/export metadata."""

    ts: str
    stage: str
    level: str
    message: str
    payload: Optional[Any] = None
    event_job_id: Optional[str] = None
    event_attempt: Optional[int] = None
    event_execution_id: Optional[str] = None
    is_requested_job_event: bool = False


class ExecutionLogResponse(BaseModel):
    """Response for GET .../aisles/{aisle_id}/jobs/{job_id}/execution-log.

    Includes envelope metadata for client-side filtering and plaintext export.
    Older clients may ignore new top-level keys; ``events`` remains the authoritative
    ordered list.
    """

    inventory_id: str
    aisle_id: str
    requested_job_id: str
    available_job_ids: List[str] = Field(default_factory=list)
    available_attempts: List[int] = Field(default_factory=list)
    available_execution_ids: List[str] = Field(default_factory=list)
    events: List[ExecutionLogEvent] = Field(default_factory=list)


class ExecutionLogJobInfo(BaseModel):
    """Per-job metadata on an aisle-level aggregated execution-log response."""

    job_id: str
    provider_name: Optional[str] = None
    model_name: Optional[str] = None
    prompt_key: Optional[str] = None
    prompt_version: Optional[str] = None
    execution_id: Optional[str] = None


class ExecutionLogSourceInfo(BaseModel):
    """Status of reading one job's execution log artifact for aggregation."""

    job_id: str
    status: Literal["ok", "missing", "error"]
    detail: Optional[str] = None


class AisleExecutionLogResponse(BaseModel):
    """Response for GET .../aisles/{aisle_id}/execution-log (multi-job aggregate)."""

    inventory_id: str
    aisle_id: str
    requested_job_id: Optional[str] = None
    available_job_ids: List[str] = Field(default_factory=list)
    available_attempts: List[int] = Field(default_factory=list)
    available_execution_ids: List[str] = Field(default_factory=list)
    jobs: List[ExecutionLogJobInfo] = Field(default_factory=list)
    log_sources: List[ExecutionLogSourceInfo] = Field(default_factory=list)
    events: List[ExecutionLogEvent] = Field(default_factory=list)

