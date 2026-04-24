"""Get capture session detail with items — Sprint 2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from src.application.errors import CaptureSessionNotFoundError, InventoryNotFoundError
from src.application.ports.capture_repositories import CaptureSessionItemRepository, CaptureSessionRepository
from src.application.ports.repositories import InventoryRepository
from src.domain.capture.entities import CaptureSession, CaptureSessionItem


@dataclass(frozen=True)
class CaptureSessionDetailResult:
    session: CaptureSession
    items: Sequence[CaptureSessionItem]


class GetCaptureSessionDetailUseCase:
    def __init__(
        self,
        *,
        inventory_repo: InventoryRepository,
        session_repo: CaptureSessionRepository,
        item_repo: CaptureSessionItemRepository,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._session_repo = session_repo
        self._item_repo = item_repo

    def execute(self, inventory_id: str, session_id: str) -> CaptureSessionDetailResult:
        if self._inventory_repo.get_by_id(inventory_id) is None:
            raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")
        session = self._session_repo.get_by_id_for_inventory(session_id, inventory_id)
        if session is None:
            raise CaptureSessionNotFoundError("Capture session not found for this inventory.")
        items = self._item_repo.list_by_session(session_id)
        return CaptureSessionDetailResult(session=session, items=items)
