"""v3.0 Aisle API schemas (request/response)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from src.api.schemas.identification_mode_literals import (
    IdentificationModeLiteral,
    IdentificationModeSourceLiteral,
)
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


class UpdateAisleRequest(BaseModel):
    """PATCH /api/v3/inventories/{inventory_id}/aisles/{aisle_id} — truly partial update."""

    code: str | None = Field(None, min_length=1, max_length=64)
    identification_mode: IdentificationModeLiteral | None = Field(
        None,
        description="Optional aisle identification override; send null to clear and inherit.",
    )

    @field_validator("code")
    @classmethod
    def strip_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("code must not be empty")
        return normalized

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> UpdateAisleRequest:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class AisleJobSummary(BaseModel):
    """Latest job summary for an aisle (optional in list response). Aligned with JobSummary for list/status contract."""

    id: str
    status: str
    created_at: datetime
    updated_at: datetime
    error_message: str | None = None
    reference_usage: ReferenceUsageSummary | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    cancel_requested_at: datetime | None = None
    current_stage: str | None = None
    current_substep: str | None = None
    current_step_started_at: datetime | None = None
    attempt_count: int = 1
    retry_of_job_id: str | None = None
    failure_code: str | None = None
    failure_message: str | None = None
    execution_id: str | None = None
    provider_name: str | None = None
    model_name: str | None = None
    prompt_key: str | None = None


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
    is_active: bool = True
    error_code: str | None = None
    error_message: str | None = None
    operational_job_id: str | None = Field(
        None, description="Canonical run for default result reads (Phase 2); null = legacy aisle."
    )
    client_supplier_id: str | None = None
    latest_job: AisleJobSummary | None = None
    assets_count: int = 0
    positions_count: int = 0
    pending_review_positions_count: int = 0
    last_activity_at: datetime | None = None
    identification_mode: IdentificationModeLiteral | None = None
    effective_identification_mode: IdentificationModeLiteral
    identification_mode_source: IdentificationModeSourceLiteral
