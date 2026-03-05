"""Stage 7 — Response schemas."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


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
    progress: Dict[str, Any] = Field(default_factory=dict)
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


class EntitiesListResponse(BaseModel):
    """GET /jobs/{job_id}/entities response."""
    entities: List[Dict[str, Any]] = Field(default_factory=list)


class EntityEvidenceResponse(BaseModel):
    """GET /jobs/{job_id}/entities/{entity_uid}/evidence response."""
    entity_uid: str
    evidence: Dict[str, Any] = Field(default_factory=dict)


class EntityAuditResponse(BaseModel):
    """GET /jobs/{job_id}/entities/{entity_uid}/audit response."""
    entity_uid: str
    events: List[Dict[str, Any]] = Field(default_factory=list)
