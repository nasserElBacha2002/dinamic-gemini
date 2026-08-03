"""API schemas for Phase 4 position reconciliation."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.domain.position_reconciliation.entities import (
    PositionReconciliation,
    ProductPositionAssignment,
)


class PositionReconciliationDto(BaseModel):
    id: str
    job_id: str
    ordered_capture_session_id: str | None = None
    reconciliation_name: str
    reconciliation_version: str
    input_fingerprint: str
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    failure_code: str | None = None
    attempt_count: int
    assigned_count: int
    unassigned_count: int
    sequence_gap_count: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductPositionAssignmentDto(BaseModel):
    id: str
    result_id: str
    source_asset_id: str
    ordered_capture_session_id: str | None = None
    sequence_number: int | None = None
    position_label_id: str | None = None
    position_name: str | None = None
    source_detection_id: str | None = None
    assignment_status: str
    assignment_reason: str
    assignment_source: str | None = None
    reconciliation_id: str
    reconciliation_version: str


class ProductPositionAssignmentListResponse(BaseModel):
    items: list[ProductPositionAssignmentDto]


def reconciliation_to_dto(row: PositionReconciliation) -> PositionReconciliationDto:
    return PositionReconciliationDto(
        id=row.id,
        job_id=row.job_id,
        ordered_capture_session_id=row.ordered_capture_session_id,
        reconciliation_name=row.reconciliation_name,
        reconciliation_version=row.reconciliation_version,
        input_fingerprint=row.input_fingerprint,
        status=row.status.value,
        started_at=row.started_at,
        completed_at=row.completed_at,
        failure_code=row.failure_code,
        attempt_count=row.attempt_count,
        assigned_count=row.assigned_count,
        unassigned_count=row.unassigned_count,
        sequence_gap_count=row.sequence_gap_count,
        metadata=dict(row.metadata_json),
    )


def assignment_to_dto(row: ProductPositionAssignment) -> ProductPositionAssignmentDto:
    return ProductPositionAssignmentDto(
        id=row.id,
        result_id=row.result_id,
        source_asset_id=row.source_asset_id,
        ordered_capture_session_id=row.ordered_capture_session_id,
        sequence_number=row.sequence_number,
        position_label_id=row.position_label_id,
        position_name=row.position_name_snapshot,
        source_detection_id=row.source_detection_id,
        assignment_status=row.assignment_status.value,
        assignment_reason=row.assignment_reason,
        assignment_source=row.assignment_source.value if row.assignment_source else None,
        reconciliation_id=row.reconciliation_id,
        reconciliation_version=row.reconciliation_version,
    )
