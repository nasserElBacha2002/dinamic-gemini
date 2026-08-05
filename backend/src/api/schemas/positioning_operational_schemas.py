"""API schemas for Phase 7 positioning operational UX."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.domain.positioning_operational.entities import (
    AisleOperationalPositioningView,
    PositioningSequenceFrame,
)


class PositioningAllowedActionsDto(BaseModel):
    process: bool = False
    reprocess: bool = False
    recover: bool = False
    review: bool = False
    correct_position: bool = False
    restore_automatic: bool = False
    reconcile_only: bool = False


class PositioningWarningDto(BaseModel):
    code: str
    title: str
    description: str
    severity: str
    affected_count: int = 0
    allowed_actions: list[str] = Field(default_factory=list)


class UnassignedCauseBucketDto(BaseModel):
    cause: str
    count: int
    suggested_action: str


class AisleOperationalPositioningViewResponse(BaseModel):
    inventory_id: str
    aisle_id: str
    client_id: str | None = None
    processing_state: str
    active_job_id: str | None = None
    result_job_id: str | None = None
    reconciliation_status: str | None = None
    reconciliation_id: str | None = None
    reconciliation_version: str | None = None
    total_results: int = 0
    assigned_results: int = 0
    unassigned_results: int = 0
    assigned_automatic: int = 0
    assigned_manual: int = 0
    unassigned_automatic: int = 0
    unassigned_manual: int = 0
    manual_overrides_count: int = 0
    invalid_positions_count: int = 0
    stale_results_count: int = 0
    unordered_assets_count: int = 0
    ambiguous_detections_count: int = 0
    detections_count: int = 0
    recoverable: bool = False
    can_process: bool = False
    can_reprocess: bool = False
    can_recover: bool = False
    can_review: bool = False
    can_correct: bool = False
    allowed_actions: PositioningAllowedActionsDto
    warnings: list[PositioningWarningDto] = Field(default_factory=list)
    unassigned_by_cause: list[UnassignedCauseBucketDto] = Field(default_factory=list)
    supported_reprocess_modes: list[str] = Field(default_factory=list)
    last_updated_at: datetime | None = None
    feature_flags: dict[str, bool] = Field(default_factory=dict)


class PositioningSequenceFrameDto(BaseModel):
    sequence_number: int | None = None
    source_asset_id: str
    filename: str | None = None
    position_detection_status: str | None = None
    position_label_name: str | None = None
    transition_action: str | None = None
    transition_message: str | None = None
    product_count: int = 0
    automatic_assignment_summaries: list[str] = Field(default_factory=list)
    effective_assignment_summaries: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    reason_code: str | None = None
    position_label_id: str | None = None


class PositioningSequenceResponse(BaseModel):
    job_id: str
    items: list[PositioningSequenceFrameDto]
    total: int
    page: int
    page_size: int


class PositioningReprocessRequest(BaseModel):
    idempotency_key: str = Field(..., min_length=8, max_length=128)
    reprocess_mode: str = Field(..., description="REPROCESS_FULL_AISLE | RECONCILE_ONLY")
    expected_active_job_id: str | None = None
    expected_result_job_id: str | None = None
    identification_mode: str | None = None


class PositioningReprocessResponse(BaseModel):
    mode: str
    job_id: str | None = None
    reconciliation_id: str | None = None
    detail: str
    manuals_preserved: bool = False
    manual_override_policy: str
    previous_manual_overrides_count: int = 0


def view_to_response(view: AisleOperationalPositioningView) -> AisleOperationalPositioningViewResponse:
    return AisleOperationalPositioningViewResponse(
        inventory_id=view.inventory_id,
        aisle_id=view.aisle_id,
        client_id=view.client_id,
        processing_state=view.processing_state,
        active_job_id=view.active_job_id,
        result_job_id=view.result_job_id,
        reconciliation_status=view.reconciliation_status,
        reconciliation_id=view.reconciliation_id,
        reconciliation_version=view.reconciliation_version,
        total_results=view.total_results,
        assigned_results=view.assigned_results,
        unassigned_results=view.unassigned_results,
        assigned_automatic=view.assigned_automatic,
        assigned_manual=view.assigned_manual,
        unassigned_automatic=view.unassigned_automatic,
        unassigned_manual=view.unassigned_manual,
        manual_overrides_count=view.manual_overrides_count,
        invalid_positions_count=view.invalid_positions_count,
        stale_results_count=view.stale_results_count,
        unordered_assets_count=view.unordered_assets_count,
        ambiguous_detections_count=view.ambiguous_detections_count,
        detections_count=view.detections_count,
        recoverable=view.recoverable,
        can_process=view.can_process,
        can_reprocess=view.can_reprocess,
        can_recover=view.can_recover,
        can_review=view.can_review,
        can_correct=view.can_correct,
        allowed_actions=PositioningAllowedActionsDto(**view.allowed_actions.as_dict()),
        warnings=[PositioningWarningDto(**w.as_dict()) for w in view.warnings],
        unassigned_by_cause=[
            UnassignedCauseBucketDto(
                cause=b.cause, count=b.count, suggested_action=b.suggested_action
            )
            for b in view.unassigned_by_cause
        ],
        supported_reprocess_modes=list(view.supported_reprocess_modes),
        last_updated_at=view.last_updated_at,
        feature_flags=dict(view.feature_flags),
    )


def frame_to_dto(frame: PositioningSequenceFrame) -> PositioningSequenceFrameDto:
    return PositioningSequenceFrameDto(
        sequence_number=frame.sequence_number,
        source_asset_id=frame.source_asset_id,
        filename=frame.filename,
        position_detection_status=frame.position_detection_status,
        position_label_name=frame.position_label_name,
        transition_action=frame.transition_action,
        transition_message=frame.transition_message,
        product_count=frame.product_count,
        automatic_assignment_summaries=list(frame.automatic_assignment_summaries),
        effective_assignment_summaries=list(frame.effective_assignment_summaries),
        warnings=list(frame.warnings),
        reason_code=frame.reason_code,
        position_label_id=frame.position_label_id,
    )
