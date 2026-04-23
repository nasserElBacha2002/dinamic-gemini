"""G4 — shared preconditions for assigning capture session groups to aisles."""

from __future__ import annotations

from src.application.errors import CaptureSessionGroupAssignmentNotAllowedError
from src.application.ports.capture_repositories import CaptureSessionGroupRepository
from src.domain.capture.entities import CaptureSession, CaptureSessionStatus


def ensure_group_aisle_assignment_allowed(
    session: CaptureSession,
    *,
    group_repo: CaptureSessionGroupRepository,
    session_id: str,
) -> None:
    """Session must be closed, non-terminal for this flow, and have at least one persisted group."""
    if session.closed_at is None:
        raise CaptureSessionGroupAssignmentNotAllowedError(
            "Aisle assignment to groups is only allowed after the capture session is closed."
        )
    if session.status in (
        CaptureSessionStatus.CANCELLED,
        CaptureSessionStatus.FAILED,
        CaptureSessionStatus.CONFIRMED,
    ):
        raise CaptureSessionGroupAssignmentNotAllowedError(
            "Aisle assignment to groups is not allowed for cancelled, failed, or confirmed capture sessions."
        )
    if group_repo.count_groups_for_session(session_id) < 1:
        raise CaptureSessionGroupAssignmentNotAllowedError(
            "Run temporal grouping (compute-groups) before assigning groups to aisles."
        )
