"""Admin finalization recovery API schemas — Phase 3.4."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AdminFinalizationRecoveryRequest(BaseModel):
    operation: str = Field(
        ...,
        description="verify | republish_artifacts | terminalize | promote | reconcile_aisle | reconcile_inventory | resume",
    )
    dry_run: bool = False
    allow_canceled_terminalization: bool = False
    include_optional_artifacts: bool = False


class AdminFinalizationRecoveryResponse(BaseModel):
    job_id: str
    operation: str
    outcome: str
    dry_run: bool
    recovery_id: str | None = None
    error_code: str | None = None
    sanitized_message: str | None = None
    previous_assessment_outcome: str
    new_assessment_outcome: str
    eligible_operations: list[str]
    blocked_operations: list[str]
    stages_attempted: list[str]
    stages_completed: list[str]
    stages_skipped: list[str]
