"""Phase 5 — published Phase 4 assignment read model (single source of truth)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from src.domain.position_reconciliation.entities import (
    AssignmentSource,
    AssignmentStatus,
    ProductPositionAssignment,
    ReconciliationStatus,
)


class PositionReadAvailability(str, Enum):
    """Why position enrichment may be absent or incomplete for a result."""

    AVAILABLE = "AVAILABLE"
    FEATURE_DISABLED = "FEATURE_DISABLED"
    NO_RECONCILIATION = "NO_RECONCILIATION"
    RECONCILIATION_STALE = "RECONCILIATION_STALE"
    UNASSIGNED = "UNASSIGNED"
    INCONSISTENT = "INCONSISTENT"


@dataclass(frozen=True)
class PublishedPositionRef:
    """Human aisle position from the published Phase 4 assignment snapshot."""

    id: str | None
    name: str | None


@dataclass(frozen=True)
class PublishedPositionAssignmentView:
    """Stable read contract for one inventory result (product_record / result_id)."""

    result_id: str
    availability: PositionReadAvailability
    position: PublishedPositionRef | None
    assignment_status: str | None
    assignment_reason: str | None
    assignment_source: str | None
    reconciliation_id: str | None
    reconciliation_version: str | None
    reconciliation_status: str | None
    sequence_number: int | None
    source_asset_id: str | None
    assigned_at: datetime | None


def map_assignment_to_view(
    assignment: ProductPositionAssignment,
    *,
    reconciliation_status: ReconciliationStatus | str | None,
) -> PublishedPositionAssignmentView:
    """Map one active assignment row to the Phase 5 read contract."""
    status_raw = reconciliation_status
    if isinstance(status_raw, ReconciliationStatus):
        status_value = status_raw.value
    elif status_raw is None:
        status_value = None
    else:
        status_value = str(status_raw).strip().upper() or None

    assigned = assignment.assignment_status is AssignmentStatus.ASSIGNED_AUTOMATIC
    name = (assignment.position_name_snapshot or "").strip() or None
    label_id = (assignment.position_label_id or "").strip() or None

    if status_value == ReconciliationStatus.STALE.value:
        availability = PositionReadAvailability.RECONCILIATION_STALE
    elif assigned and name:
        availability = PositionReadAvailability.AVAILABLE
    else:
        availability = PositionReadAvailability.UNASSIGNED

    position = (
        PublishedPositionRef(id=label_id, name=name)
        if assigned and (label_id or name)
        else None
    )
    source = (
        assignment.assignment_source.value
        if isinstance(assignment.assignment_source, AssignmentSource)
        else (str(assignment.assignment_source) if assignment.assignment_source else None)
    )
    return PublishedPositionAssignmentView(
        result_id=assignment.result_id,
        availability=availability,
        position=position,
        assignment_status=assignment.assignment_status.value,
        assignment_reason=assignment.assignment_reason or None,
        assignment_source=source,
        reconciliation_id=assignment.reconciliation_id,
        reconciliation_version=assignment.reconciliation_version,
        reconciliation_status=status_value,
        sequence_number=assignment.sequence_number,
        source_asset_id=assignment.source_asset_id,
        assigned_at=assignment.created_at if assigned else None,
    )


def no_reconciliation_view(result_id: str) -> PublishedPositionAssignmentView:
    return PublishedPositionAssignmentView(
        result_id=result_id,
        availability=PositionReadAvailability.NO_RECONCILIATION,
        position=None,
        assignment_status="NO_RECONCILIATION",
        assignment_reason=None,
        assignment_source=None,
        reconciliation_id=None,
        reconciliation_version=None,
        reconciliation_status=None,
        sequence_number=None,
        source_asset_id=None,
        assigned_at=None,
    )


def feature_disabled_view(result_id: str) -> PublishedPositionAssignmentView:
    return PublishedPositionAssignmentView(
        result_id=result_id,
        availability=PositionReadAvailability.FEATURE_DISABLED,
        position=None,
        assignment_status=None,
        assignment_reason=None,
        assignment_source=None,
        reconciliation_id=None,
        reconciliation_version=None,
        reconciliation_status=None,
        sequence_number=None,
        source_asset_id=None,
        assigned_at=None,
    )
