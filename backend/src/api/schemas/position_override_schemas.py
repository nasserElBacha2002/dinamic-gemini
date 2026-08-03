"""v3 API contracts for manual product-position overrides."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.domain.position_overrides.entities import (
    EffectiveProductPositionView,
    ManualProductPositionOverride,
    PositionOverrideAction,
    PositionOverrideReasonCode,
)
from src.domain.position_reconciliation.entities import ProductPositionAssignment


class PositionOverrideRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: PositionOverrideAction
    position_label_id: str | None = None
    reason_code: PositionOverrideReasonCode
    reason_text: str | None = Field(default=None, max_length=1000)
    expected_version: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1, max_length=128)


class RestoreAutomaticRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason_code: PositionOverrideReasonCode = (
        PositionOverrideReasonCode.OPERATOR_VERIFICATION
    )
    reason_text: str | None = Field(default=None, max_length=1000)
    expected_version: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1, max_length=128)


class PositionRefResponse(BaseModel):
    id: str | None = None
    name: str | None = None


class ManualOverrideResponse(BaseModel):
    id: str
    action: PositionOverrideAction
    reason_code: PositionOverrideReasonCode
    reason_text: str | None
    position_label_id: str | None
    position_name: str | None
    created_by_user_id: str
    created_by_role: str
    created_at: datetime
    deactivated_at: datetime | None
    version: int
    is_active: bool


class EffectivePositionResponse(BaseModel):
    result_id: str
    position: PositionRefResponse | None
    source: str
    status: str
    automatic_position: PositionRefResponse | None
    automatic_assignment_status: str | None
    automatic_assignment_id: str | None
    automatic_reconciliation_id: str | None
    reconciliation_status: str | None
    manual_override: ManualOverrideResponse | None
    warnings: list[str]
    version: int


class PositionOverrideMutationResponse(BaseModel):
    revision: ManualOverrideResponse
    current_effective: EffectivePositionResponse


class PositionHistoryResponse(BaseModel):
    effective: EffectivePositionResponse
    automatic_revisions: list[AutomaticAssignmentHistoryResponse]
    manual_revisions: list[ManualOverrideResponse]


class AutomaticAssignmentHistoryResponse(BaseModel):
    id: str
    reconciliation_id: str
    position_label_id: str | None
    position_name: str | None
    assignment_status: str
    assignment_reason: str
    is_active: bool
    created_at: datetime
    superseded_at: datetime | None


def automatic_to_history_response(
    row: ProductPositionAssignment,
) -> AutomaticAssignmentHistoryResponse:
    return AutomaticAssignmentHistoryResponse(
        id=row.id,
        reconciliation_id=row.reconciliation_id,
        position_label_id=row.position_label_id,
        position_name=row.position_name_snapshot,
        assignment_status=row.assignment_status.value,
        assignment_reason=row.assignment_reason,
        is_active=row.is_active,
        created_at=row.created_at,
        superseded_at=row.superseded_at,
    )


def override_to_response(row: ManualProductPositionOverride) -> ManualOverrideResponse:
    return ManualOverrideResponse(
        id=row.id,
        action=row.override_action,
        reason_code=row.reason_code,
        reason_text=row.reason_text,
        position_label_id=row.new_position_label_id,
        position_name=row.new_position_name_snapshot,
        created_by_user_id=row.created_by_user_id,
        created_by_role=row.created_by_role,
        created_at=row.created_at,
        deactivated_at=row.deactivated_at,
        version=row.version,
        is_active=row.is_active,
    )


def effective_to_response(row: EffectiveProductPositionView) -> EffectivePositionResponse:
    return EffectivePositionResponse(
        result_id=row.result_id,
        position=(
            PositionRefResponse(id=row.effective_position.id, name=row.effective_position.name)
            if row.effective_position
            else None
        ),
        source=row.effective_source.value,
        status=row.effective_status,
        automatic_position=(
            PositionRefResponse(id=row.automatic_position.id, name=row.automatic_position.name)
            if row.automatic_position
            else None
        ),
        automatic_assignment_status=row.automatic_assignment_status,
        automatic_assignment_id=row.automatic_assignment_id,
        automatic_reconciliation_id=row.automatic_reconciliation_id,
        reconciliation_status=row.reconciliation_status,
        manual_override=(
            override_to_response(row.manual_override) if row.manual_override else None
        ),
        warnings=list(row.warnings),
        version=row.version,
    )
