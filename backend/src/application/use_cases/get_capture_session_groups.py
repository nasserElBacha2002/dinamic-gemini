"""G3 — read persisted temporal groups for a capture session."""

from __future__ import annotations

from typing import Sequence

from src.application.errors import CaptureSessionNotFoundError
from src.application.ports.capture_repositories import (
    CaptureSessionGroupRepository,
    CaptureSessionGroupSummary,
    CaptureSessionRepository,
)


class GetCaptureSessionGroupsUseCase:
    def __init__(
        self,
        *,
        session_repo: CaptureSessionRepository,
        group_repo: CaptureSessionGroupRepository,
    ) -> None:
        self._session_repo = session_repo
        self._group_repo = group_repo

    def execute(self, *, inventory_id: str, session_id: str) -> Sequence[CaptureSessionGroupSummary]:
        session = self._session_repo.get_by_id_for_inventory(session_id, inventory_id)
        if session is None:
            raise CaptureSessionNotFoundError(
                "Capture session not found for this inventory (session id does not match inventory scope)."
            )
        return self._group_repo.list_summaries(session_id)
