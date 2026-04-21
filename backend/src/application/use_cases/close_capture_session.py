"""Close capture session — Sprint 2 (import finished, ready for downstream review).

Semantics (explicit, merge-safe):

* ``IMPORTING`` → ``READY_FOR_REVIEW``: allowed once import work is finished (at least one
  successful staging row exists, because status only becomes ``IMPORTING`` after an
  ``IMPORTED`` item is saved).

* ``DRAFT`` → ``READY_FOR_REVIEW``: **not** allowed when the session has **no** rows with
  ``import_status == IMPORTED``. An empty draft cannot be "ready for review" without
  preview/confirm flows (out of scope); use **cancel** to discard. This avoids an
  ambiguous empty session labeled ready for review.

* ``READY_FOR_REVIEW`` with ``closed_at`` unset: idempotent close sets ``closed_at``.

* Terminal / future states: unchanged rejections.
"""

from __future__ import annotations

from src.application.errors import CaptureSessionInvalidStateError, CaptureSessionNotFoundError
from src.application.ports.capture_repositories import CaptureSessionItemRepository, CaptureSessionRepository
from src.application.ports.clock import Clock
from src.domain.capture.entities import CaptureSession, CaptureSessionItemImportStatus, CaptureSessionStatus

_ALLOWED_CLOSE_STATUSES = frozenset(
    {
        CaptureSessionStatus.DRAFT,
        CaptureSessionStatus.IMPORTING,
    }
)


class CloseCaptureSessionUseCase:
    def __init__(
        self,
        *,
        session_repo: CaptureSessionRepository,
        item_repo: CaptureSessionItemRepository,
        clock: Clock,
    ) -> None:
        self._session_repo = session_repo
        self._item_repo = item_repo
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
        if session.status == CaptureSessionStatus.DRAFT:
            imported = self._item_repo.count_items_with_import_status(
                session_id, CaptureSessionItemImportStatus.IMPORTED
            )
            if imported < 1:
                raise CaptureSessionInvalidStateError(
                    "Cannot close a draft capture session with no successfully imported items; "
                    "upload media or cancel the session."
                )
        session.status = CaptureSessionStatus.READY_FOR_REVIEW
        session.closed_at = now
        session.updated_at = now
        self._session_repo.save(session)
        return session
