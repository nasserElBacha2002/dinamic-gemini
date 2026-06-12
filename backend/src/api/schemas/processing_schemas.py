"""v3.0 Processing API schemas (process, status)."""

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from src.api.schemas.aisle_schemas import AisleResponse
from src.api.schemas.benchmark_schemas import LlmCostSnapshotResponse
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
        description=(
            "Ignored for hybrid body selection: new aisle jobs always use profile global_v22 (label-first). "
            "Listed keys (global_v21, global_v21_b, global_v22) remain valid for admin/options; "
            "HYBRID_PROMPT affects documentation and non-pipeline defaults only."
        ),
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
    models: list[ProcessingModelOption] = Field(default_factory=list)
    default_model: Optional[str] = Field(
        None, description="Default model id for this provider when model_name is omitted."
    )
    production_available: Optional[bool] = Field(
        None,
        description="True when provider has credentials and a default production model (test catalog only).",
    )
    unavailable_reason: Optional[str] = Field(
        None,
        description="Why the provider is not production-ready; omitted when production_available is true.",
    )
    is_default_provider: bool = Field(
        False,
        description="True when this provider matches server default (LLM_PROVIDER).",
    )


class ProcessingProviderOptionsResponse(BaseModel):
    """GET /api/v3/inventories/processing-provider-options — discovery for POST process."""

    mode: Literal["test", "production"] = Field(
        "test",
        description=(
            "Catalog scope: test lists all configured models; production lists one model per "
            "provider from explicit env (GEMINI_MODEL_NAME, OPENAI_MODEL, ANTHROPIC_MODEL) only."
        ),
    )
    default_provider_key: str
    default_model_key: Optional[str] = Field(
        None,
        description="Default model id for default_provider_key in this catalog mode.",
    )
    default_prompt_key: str
    prompt_profiles: list[ProcessingPromptOptionItem] = Field(default_factory=list)
    providers: list[ProcessingProviderOptionItem] = Field(default_factory=list)


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
    finalization_status: Optional[str] = None
    current_finalization_step: Optional[str] = None
    last_completed_finalization_step: Optional[str] = None
    finalization_error_code: Optional[str] = None
    #: True when this job is the aisle ``operational_job_id`` pointer (Phase 6 run browser).
    is_operational: bool = False
    #: Optional LLM cost snapshot from ``result_json`` (sanitized; additive for run pickers).
    llm_cost_snapshot: Optional[LlmCostSnapshotResponse] = None


class FinalizationStageAssessmentItem(BaseModel):
    """Sanitized per-stage finalization evidence for job detail."""

    stage: str
    status: str
    evidence_level: str
    completed_at: Optional[datetime] = None
    verification_required: bool = False
    last_error_code: Optional[str] = None


class FinalizationAssessmentBlock(BaseModel):
    """Read-only finalization assessment (Phase 3.3)."""

    outcome: str
    technical_result_status: str
    finalization_status: str
    last_confirmed_stage: Optional[str] = None
    next_required_stage: Optional[str] = None
    recovery_candidate: bool = False
    blocking_reason: Optional[str] = None
    stages: dict[str, FinalizationStageAssessmentItem] = Field(default_factory=dict)


class ArtifactPublicationItemResponse(BaseModel):
    artifact_kind: str
    required: bool
    status: str
    attempt_count: int = 0
    max_attempts: int = 5
    next_attempt_at: Optional[datetime] = None
    last_error_code: Optional[str] = None
    source_type: Optional[str] = None


class ArtifactPublicationBlock(BaseModel):
    required_total: int = 0
    required_published: int = 0
    pending: int = 0
    retry_scheduled: int = 0
    permanently_failed: int = 0
    next_attempt_at: Optional[datetime] = None
    items: list[ArtifactPublicationItemResponse] = Field(default_factory=list)


class JobDetailResponse(JobSummary):
    """Extended job detail for GET .../jobs/{job_id} — finalization timestamps and diagnostics."""

    finalization_started_at: Optional[datetime] = None
    finalization_completed_at: Optional[datetime] = None
    domain_persisted_at: Optional[datetime] = None
    artifacts_published_at: Optional[datetime] = None
    finalization_error_metadata: Optional[dict[str, Any]] = None
    finalization_assessment: Optional[FinalizationAssessmentBlock] = None
    artifact_publication: Optional[ArtifactPublicationBlock] = None


class AisleStatusResponse(BaseModel):
    """Response for GET .../aisles/{aisle_id}/status."""

    aisle: AisleResponse
    latest_job: Optional[JobSummary] = None
    operational_job_id: Optional[str] = None
    recent_jobs: list[JobSummary] = Field(default_factory=list)


class AisleJobsListResponse(BaseModel):
    """Response for GET .../aisles/{aisle_id}/jobs (Phase 2 run browser)."""

    operational_job_id: Optional[str] = None
    jobs: list[JobSummary] = Field(default_factory=list)


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
    available_job_ids: list[str] = Field(default_factory=list)
    available_attempts: list[int] = Field(default_factory=list)
    available_execution_ids: list[str] = Field(default_factory=list)
    events: list[ExecutionLogEvent] = Field(default_factory=list)


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
    available_job_ids: list[str] = Field(default_factory=list)
    available_attempts: list[int] = Field(default_factory=list)
    available_execution_ids: list[str] = Field(default_factory=list)
    jobs: list[ExecutionLogJobInfo] = Field(default_factory=list)
    log_sources: list[ExecutionLogSourceInfo] = Field(default_factory=list)
    events: list[ExecutionLogEvent] = Field(default_factory=list)
