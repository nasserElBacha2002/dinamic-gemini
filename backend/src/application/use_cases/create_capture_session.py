"""Create capture session — Sprint 2 (concurrency + scope validation)."""

from __future__ import annotations

from uuid import uuid4

from src.application.errors import InventoryNotFoundError, OpenCaptureSessionExistsError
from src.application.ports.capture_repositories import CaptureSessionRepository
from src.application.ports.clock import Clock
from src.application.ports.repositories import AisleRepository, InventoryRepository
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.domain.capture.entities import CaptureSession, CaptureSessionStatus


class CreateCaptureSessionUseCase:
    def __init__(
        self,
        *,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        session_repo: CaptureSessionRepository,
        clock: Clock,
        max_open_sessions_per_aisle: int,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._session_repo = session_repo
        self._clock = clock
        self._max_open = max(1, int(max_open_sessions_per_aisle))

    def execute(self, inventory_id: str, aisle_id: str) -> CaptureSession:
        if self._inventory_repo.get_by_id(inventory_id) is None:
            raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")
        require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            detail_style="strict",
        )
        open_count = self._session_repo.count_open_sessions_for_aisle(inventory_id, aisle_id)
        if open_count >= self._max_open:
            raise OpenCaptureSessionExistsError(
                "An open capture session already exists for this aisle; close or cancel it first."
            )
        now = self._clock.now()
        session = CaptureSession(
            id=str(uuid4()),
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            status=CaptureSessionStatus.DRAFT,
            created_at=now,
            updated_at=now,
            opened_at=now,
            closed_at=None,
        )
        self._session_repo.save(session)
        return session
