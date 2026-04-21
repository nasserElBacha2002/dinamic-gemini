"""Close capture session — Sprint 2 (import finished, ready for downstream review)."""

from __future__ import annotations

from src.application.errors import CaptureSessionInvalidStateError, CaptureSessionNotFoundError
from src.application.ports.capture_repositories import CaptureSessionRepository
from src.application.ports.clock import Clock
from src.domain.capture.entities import CaptureSession, CaptureSessionStatus

_ALLOWED_CLOSE_STATUSES = frozenset(
    {
        CaptureSessionStatus.DRAFT,
        CaptureSessionStatus.IMPORTING,
    }
)


class CloseCaptureSessionUseCase:
    def __init__(self, *, session_repo: CaptureSessionRepository, clock: Clock) -> None:
        self._session_repo = session_repo
        self._clock = clock

    def execute(self, *, inventory_id: str, aisle_id: str, session_id: str) -> CaptureSession:
        session = self._session_repo.get_by_id_for_inventory(session_id, inventory_id)
        if session is None or session.aisle_id != aisle_id:
            raise CaptureSessionNotFoundError("Capture session not found for this inventory and aisle.")
        if session.status == CaptureSessionStatus.CANCELLED:
            raise CaptureSessionInvalidStateError("Cannot close a cancelled capture session.")
        if session.status == CaptureSessionStatus.CONFIRMED:
            raise CaptureSessionInvalidStateError("Cannot close a confirmed capture session.")
        if session.status == CaptureSessionStatus.FAILED:
            raise CaptureSessionInvalidStateError("Cannot close a failed capture session.")
        if session.status in (
            CaptureSessionStatus.ASSIGNMENT_PROPOSED,
            CaptureSessionStatus.CONFIRMING,
        ):
            raise CaptureSessionInvalidStateError("Cannot close a capture session in this state.")
        now = self._clock.now()
        if session.closed_at is not None and session.status == CaptureSessionStatus.READY_FOR_REVIEW:
            return session
        if session.status == CaptureSessionStatus.READY_FOR_REVIEW and session.closed_at is None:
            session.closed_at = now
            session.updated_at = now
            self._session_repo.save(session)
            return session
        if session.status not in _ALLOWED_CLOSE_STATUSES:
            raise CaptureSessionInvalidStateError("Cannot close a capture session in this state.")
        session.status = CaptureSessionStatus.READY_FOR_REVIEW
        session.closed_at = now
        session.updated_at = now
        self._session_repo.save(session)
        return session
