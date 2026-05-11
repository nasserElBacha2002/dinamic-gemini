"""v3.0 Aisle API schemas (request/response)."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from src.api.schemas.reference_usage_schemas import ReferenceUsageSummary


class CreateAisleRequest(BaseModel):
    """POST /api/v3/inventories/{inventory_id}/aisles body."""

    code: str = Field(..., min_length=1, max_length=64)
    client_supplier_id: str | None = Field(
        None,
        description=(
            "Supplier for this aisle. Required when the inventory has a client; "
            "omit only if supported by legacy tooling (API validates against inventory)."
        ),
    )

    @field_validator("client_supplier_id")
    @classmethod
    def validate_client_supplier_id_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("client_supplier_id must not be empty")
        return normalized


class AisleJobSummary(BaseModel):
    """Latest job summary for an aisle (optional in list response). Aligned with JobSummary for list/status contract."""

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


class AisleResponse(BaseModel):
    """Aisle payload for create, status, and list endpoints.

    The same model carries a minimal aisle (create / polling) and—on GET list—optional
    rollups for the Inventory Detail table. Callers should treat unset rollup defaults
    (0 / null) as “not computed for this response” until a dedicated split is justified.
    """

    id: str
    inventory_id: str
    code: str
    status: str
    created_at: datetime
    updated_at: datetime
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    operational_job_id: Optional[str] = Field(
        None, description="Canonical run for default result reads (Phase 2); null = legacy aisle."
    )
    client_supplier_id: Optional[str] = None
    latest_job: Optional[AisleJobSummary] = None
    assets_count: int = 0
    positions_count: int = 0
    pending_review_positions_count: int = 0
    last_activity_at: Optional[datetime] = None
