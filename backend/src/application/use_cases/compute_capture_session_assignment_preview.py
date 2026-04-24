"""Compute deterministic aisle-position assignment preview — Sprint 3 (no SourceAsset).

Loads aisle ``Position`` rows via :meth:`PositionRepository.list_by_aisle` (default job slice =
all rows for the aisle) and runs :func:`compute_item_preview_outcomes` — an **explicit MVP
heuristic** (ordinal pairing by sorted time vs sorted position code), not optical slotting.
See ``capture_assignment_preview`` module docstring.
"""

from __future__ import annotations

from src.application.errors import CaptureSessionNotFoundError, CaptureSessionPreviewNotAllowedError
from src.application.ports.capture_repositories import CaptureSessionItemRepository, CaptureSessionRepository
from src.application.ports.clock import Clock
from src.application.ports.repositories import JOB_ID_FILTER_UNSET, PositionRepository
from src.application.services.capture_assignment_preview import compute_item_preview_outcomes
from src.domain.capture.entities import CaptureSession, CaptureSessionStatus

_PREVIEW_ALLOWED = frozenset(
    {
        CaptureSessionStatus.READY_FOR_REVIEW,
        CaptureSessionStatus.ASSIGNMENT_PROPOSED,
    }
)


class ComputeCaptureSessionAssignmentPreviewUseCase:
    def __init__(
        self,
        *,
        session_repo: CaptureSessionRepository,
        item_repo: CaptureSessionItemRepository,
        position_repo: PositionRepository,
        clock: Clock,
        preview_max_positions: int,
    ) -> None:
        self._session_repo = session_repo
        self._item_repo = item_repo
        self._position_repo = position_repo
        self._clock = clock
        self._preview_max_positions = max(1, int(preview_max_positions))

    def execute(self, *, inventory_id: str, aisle_id: str, session_id: str) -> CaptureSession:
        session = self._session_repo.get_by_id_for_inventory(session_id, inventory_id)
        if session is None or session.aisle_id != aisle_id:
            raise CaptureSessionNotFoundError("Capture session not found for this inventory and aisle.")
        if session.status not in _PREVIEW_ALLOWED:
            raise CaptureSessionPreviewNotAllowedError(
                "Assignment preview is only allowed when the session is ready_for_review or assignment_proposed."
            )
        if session.closed_at is None:
            raise CaptureSessionPreviewNotAllowedError(
                "Assignment preview requires the capture session to be closed (ready for review)."
            )
        items = list(self._item_repo.list_by_session(session_id))
        positions = list(
            self._position_repo.list_by_aisle(
                aisle_id,
                page=1,
                page_size=self._preview_max_positions,
                job_id=JOB_ID_FILTER_UNSET,
            )
        )
        outcomes = compute_item_preview_outcomes(
            items=items,
            positions=positions,
            clock_offset_seconds=session.clock_offset_seconds,
        )
        now = self._clock.now()
        for it in items:
            row = outcomes.get(it.id)
            if row is None:
                continue
            it.assignment_status = row.assignment_status
            it.assignment_reason = row.assignment_reason
            it.adjusted_capture_time = row.adjusted_capture_time
            it.preview_target_position_id = row.preview_target_position_id
            it.updated_at = now
            self._item_repo.save(it)
        session.status = CaptureSessionStatus.ASSIGNMENT_PROPOSED
        session.updated_at = now
        self._session_repo.save(session)
        return session

