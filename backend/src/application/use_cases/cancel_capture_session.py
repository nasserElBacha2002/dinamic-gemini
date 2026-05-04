"""Cancel capture session — Sprint 2 (terminal cancel + safe staging cleanup)."""

from __future__ import annotations

import logging

from src.application.errors import CaptureSessionInvalidStateError, CaptureSessionNotFoundError
from src.application.ports.capture_repositories import (
    CaptureSessionItemRepository,
    CaptureSessionRepository,
)
from src.application.ports.clock import Clock
from src.application.ports.services import ArtifactStorage
from src.domain.capture.entities import CaptureSession, CaptureSessionStatus

logger = logging.getLogger(__name__)


class CancelCaptureSessionUseCase:
    def __init__(
        self,
        *,
        session_repo: CaptureSessionRepository,
        item_repo: CaptureSessionItemRepository,
        artifact_storage: ArtifactStorage,
        clock: Clock,
    ) -> None:
        self._session_repo = session_repo
        self._item_repo = item_repo
        self._artifact_storage = artifact_storage
        self._clock = clock

    def execute(
        self, *, inventory_id: str, session_id: str, aisle_id: str | None = None
    ) -> CaptureSession:
        session = self._session_repo.get_by_id_for_inventory(session_id, inventory_id)
        if session is None:
            raise CaptureSessionNotFoundError(
                "Capture session not found for this inventory and aisle."
            )
        if aisle_id is not None and session.aisle_id != aisle_id:
            raise CaptureSessionNotFoundError(
                "Capture session not found for this inventory and aisle."
            )
        if session.status == CaptureSessionStatus.CONFIRMED:
            raise CaptureSessionInvalidStateError("Cannot cancel a confirmed capture session.")
        if session.status == CaptureSessionStatus.CANCELLED:
            return session
        now = self._clock.now()
        session.status = CaptureSessionStatus.CANCELLED
        session.closed_at = now
        session.updated_at = now
        self._session_repo.save(session)
        for item in self._item_repo.list_staging_cleanup_candidates(session_id):
            if item.linked_source_asset_id:
                continue
            key = (item.staging_storage_key or "").strip()
            if not key:
                continue
            try:
                self._artifact_storage.delete_file(key)
            except Exception as exc:  # noqa: BLE001 — best-effort cleanup
                logger.warning(
                    "capture_session cancel: staging delete failed session_id=%s item_id=%s key=%s: %s",
                    session_id,
                    item.id,
                    key,
                    exc,
                )
        return session
