"""Update session-level clock offset (Sprint 3); invalidates stored preview deterministically."""

from __future__ import annotations

from src.application.errors import (
    CaptureSessionInvalidClockOffsetError,
    CaptureSessionInvalidStateError,
    CaptureSessionNotFoundError,
)
from src.application.ports.capture_repositories import (
    CaptureSessionItemRepository,
    CaptureSessionRepository,
)
from src.application.ports.clock import Clock
from src.domain.capture.entities import (
    CaptureSession,
    CaptureSessionItemAssignmentStatus,
    CaptureSessionItemImportStatus,
    CaptureSessionStatus,
)

_BLOCKED_STATUSES = frozenset(
    {
        CaptureSessionStatus.CANCELLED,
        CaptureSessionStatus.FAILED,
        CaptureSessionStatus.CONFIRMED,
        CaptureSessionStatus.CONFIRMING,
    }
)


class UpdateCaptureSessionClockOffsetUseCase:
    def __init__(
        self,
        *,
        session_repo: CaptureSessionRepository,
        item_repo: CaptureSessionItemRepository,
        clock: Clock,
        min_offset_seconds: int,
        max_offset_seconds: int,
    ) -> None:
        self._session_repo = session_repo
        self._item_repo = item_repo
        self._clock = clock
        self._min_off = int(min_offset_seconds)
        self._max_off = int(max_offset_seconds)

    def execute(
        self, *, inventory_id: str, aisle_id: str, session_id: str, clock_offset_seconds: int
    ) -> CaptureSession:
        if clock_offset_seconds < self._min_off or clock_offset_seconds > self._max_off:
            raise CaptureSessionInvalidClockOffsetError(
                f"clock_offset_seconds must be between {self._min_off} and {self._max_off} inclusive"
            )
        session = self._session_repo.get_by_id_for_inventory(session_id, inventory_id)
        if session is None or session.aisle_id != aisle_id:
            raise CaptureSessionNotFoundError(
                "Capture session not found for this inventory and aisle."
            )
        if session.status in _BLOCKED_STATUSES:
            raise CaptureSessionInvalidStateError(
                "Clock offset cannot be updated for this capture session state."
            )
        now = self._clock.now()
        items = list(self._item_repo.list_by_session(session_id))
        if session.status == CaptureSessionStatus.ASSIGNMENT_PROPOSED:
            session.status = CaptureSessionStatus.READY_FOR_REVIEW
        session.clock_offset_seconds = int(clock_offset_seconds)
        session.updated_at = now
        for it in items:
            if it.import_status != CaptureSessionItemImportStatus.IMPORTED:
                continue
            it.assignment_status = CaptureSessionItemAssignmentStatus.PENDING
            it.adjusted_capture_time = None
            it.assignment_reason = None
            it.preview_target_position_id = None
            it.updated_at = now
            self._item_repo.save(it)
        self._session_repo.save(session)
        return session
