"""Stage 7 — Request schemas (validation)."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class JobCreateForm(BaseModel):
    """Parsed form fields for POST /jobs."""
    mode: str = Field(default="legacy", pattern="^(legacy|hybrid)$")
    confidence_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    metadata: Optional[Any] = None
