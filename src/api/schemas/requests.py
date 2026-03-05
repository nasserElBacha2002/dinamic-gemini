"""Stage 7 — Request schemas (validation)."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class JobCreateForm(BaseModel):
    """Parsed form fields for POST /jobs."""
    mode: str = Field(default="legacy", pattern="^(legacy|hybrid)$")
    confidence_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    metadata: Optional[Any] = None


class ReviewSubmitBody(BaseModel):
    """POST /jobs/{job_id}/entities/{entity_uid}/review body."""
    action: str = Field(..., description="SET_COUNT | MARK_EMPTY | MARK_INVALID")
    final_quantity: Optional[int] = Field(None, ge=0, description="Required for SET_COUNT.")
    actor: str = Field("", description="Identifier of who performed the review.")
    notes: Optional[str] = None
