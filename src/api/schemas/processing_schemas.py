"""v3.0 Processing API schemas (process, status)."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from src.api.schemas.aisle_schemas import AisleResponse


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


class AisleStatusResponse(BaseModel):
    """Response for GET .../aisles/{aisle_id}/status."""
    aisle: AisleResponse
    latest_job: Optional[JobSummary] = None

