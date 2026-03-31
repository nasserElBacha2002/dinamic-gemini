"""Compact reference-image usage summary contracts for operator-facing job surfaces."""

from typing import List, Optional

from pydantic import BaseModel, Field


class ReferenceUsageSummary(BaseModel):
    """Stable summary derived from job.result_json.visual_reference_context."""

    resolved: bool = False
    resolved_count: int = 0
    provider_consumed: bool = False
    provider_consumed_count: int = 0
    reference_ids: List[str] = Field(default_factory=list)
    resolution_error: Optional[str] = None
