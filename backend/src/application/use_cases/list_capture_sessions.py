"""List capture sessions for an inventory — Sprint 2."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from src.application.errors import InventoryNotFoundError
from src.application.ports.capture_repositories import CaptureSessionRepository
from src.application.ports.repositories import InventoryRepository
from src.domain.capture.entities import CaptureSession, CaptureSessionStatus


@dataclass(frozen=True)
class ListCaptureSessionsResult:
    items: Sequence[CaptureSession]
    total_items: int
    page: int
    page_size: int


class ListCaptureSessionsUseCase:
    def __init__(
        self,
        *,
        inventory_repo: InventoryRepository,
        session_repo: CaptureSessionRepository,
        default_page_size: int,
        max_page_size: int,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._session_repo = session_repo
        self._default_page_size = max(1, int(default_page_size))
        self._max_page_size = max(1, int(max_page_size))

    def execute(
        self,
        inventory_id: str,
        *,
        aisle_id: str | None = None,
        statuses: Sequence[CaptureSessionStatus] | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        page: int = 1,
        page_size: int | None = None,
    ) -> ListCaptureSessionsResult:
        if self._inventory_repo.get_by_id(inventory_id) is None:
            raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")
        ps = int(page_size) if page_size is not None else self._default_page_size
        ps = max(1, min(ps, self._max_page_size))
        pg = max(1, int(page))
        rows, total = self._session_repo.list_by_inventory(
            inventory_id,
            aisle_id=aisle_id,
            statuses=statuses,
            created_from=created_from,
            created_to=created_to,
            page=pg,
            page_size=ps,
        )
        return ListCaptureSessionsResult(items=rows, total_items=total, page=pg, page_size=ps)
