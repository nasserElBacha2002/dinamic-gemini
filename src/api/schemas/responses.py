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
