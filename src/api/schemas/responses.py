"""Stage 7 — Response schemas."""

from typing import Any, Dict, List, Literal, Optional, TypedDict

from pydantic import BaseModel, Field

# Epic 3.1.B: constrained traceability status (backward compatible: optional)
TraceabilityStatusLiteral = Literal["valid", "missing", "invalid", "unvalidated"]
TRACEABILITY_STATUS_VALUES = frozenset({"valid", "missing", "invalid", "unvalidated"})


class ProgressDict(TypedDict):
    """Job progress: stage name and percent (0–100). Used in JobStatusResponse."""
    stage: str
    percent: int


class JobCreateResponse(BaseModel):
    """202 response after creating a job."""
    job_id: str
    status: str = "queued"
    mode: str
    confidence_threshold: float = 0.70


class JobStatusResponse(BaseModel):
    """GET /jobs/{job_id} response."""
    job_id: str
    status: str
    progress: ProgressDict = Field(default_factory=lambda: {"stage": "", "percent": 0})
    created_at: str = ""
    execution_time_seconds: Optional[float] = Field(default=None, description="Tiempo de ejecución en segundos (cuando el trabajo ha terminado).")


class ArtifactItem(BaseModel):
    """Single artifact entry."""
    name: str
    path: str


class ArtifactsResponse(BaseModel):
    """GET /jobs/{job_id}/artifacts response."""
    job_id: str
    artifacts: List[ArtifactItem] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """GET /health response."""
    ok: bool = True


class EntityListItem(BaseModel):
    """Single entity in GET /jobs/{job_id}/entities response."""
    entity_uid: str
    pallet_id: Optional[str] = None
    entity_type: str
    count_status: Optional[str] = None
    entity_quality_score: Optional[float] = None
    evidence_ref: Optional[str] = Field(None, description="evidence_path or ref to evidence.")
    source_image_id: Optional[str] = Field(None, description="Epic 3.1.B: image_id of source image for this entity.")
    traceability_status: Optional[TraceabilityStatusLiteral] = Field(
        None,
        description="Epic 3.1.B: valid | missing | invalid | unvalidated.",
    )
    traceability_warning: Optional[str] = Field(
        None,
        description="Epic 3.1.B: diagnostic only (e.g. reason when status is invalid); not persisted to DB.",
    )


class TraceabilitySummary(BaseModel):
    """Epic 3.1.C: job-level traceability counts for review/audit. Always reflects the full job, not the filtered result set."""

    total_entities: int = Field(..., description="Total number of entities in the job report.")
    valid: int = Field(0, description="Entities with traceability_status=valid.")
    missing: int = Field(0, description="Entities with traceability_status=missing or legacy/unknown.")
    invalid: int = Field(0, description="Entities with traceability_status=invalid.")
    unvalidated: int = Field(0, description="Entities with traceability_status=unvalidated.")


class EntitiesListResponse(BaseModel):
    """GET /jobs/{job_id}/entities response.

    Epic 3.1.C: traceability_summary, when present, is always the full-job summary
    (counts over all entities in the report), regardless of status/entity_type filters.
    """

    entities: List[EntityListItem] = Field(default_factory=list)
    traceability_summary: Optional[TraceabilitySummary] = Field(
        None,
        description="Full-job traceability counts (valid, missing, invalid, unvalidated). Omitted for legacy reports without traceability.",
    )


class EntityEvidenceResponse(BaseModel):
    """GET /jobs/{job_id}/entities/{entity_uid}/evidence response.
    evidence: flexible dict (paths/refs per entity); shape may evolve with pipeline."""
    entity_uid: str
    evidence: Dict[str, Any] = Field(default_factory=dict)


class EntityAuditResponse(BaseModel):
    """GET /jobs/{job_id}/entities/{entity_uid}/audit response.
    events: list of review event dicts (timestamp, actor, action, before, after, notes); kept flexible for audit schema evolution."""
    entity_uid: str
    events: List[Dict[str, Any]] = Field(default_factory=list)


class ReviewSubmitResponse(BaseModel):
    """POST /jobs/{job_id}/entities/{entity_uid}/review response."""
    entity_uid: str
    action: str
    message: str
