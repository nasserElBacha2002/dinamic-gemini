"""In-memory CaptureSessionRepository — Sprint 2."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional, Sequence

from src.application.ports.capture_repositories import CaptureSessionRepository
from src.domain.capture.entities import CaptureSession, CaptureSessionStatus

_TERMINAL_OPEN_BLOCK = frozenset(
    {
        CaptureSessionStatus.CANCELLED,
        CaptureSessionStatus.FAILED,
        CaptureSessionStatus.CONFIRMED,
    }
)


class MemoryCaptureSessionRepository(CaptureSessionRepository):
    def __init__(self) -> None:
        self._store: Dict[str, CaptureSession] = {}

    def save(self, session: CaptureSession) -> None:
        self._store[session.id] = session

    def get_by_id(self, session_id: str) -> Optional[CaptureSession]:
        return self._store.get(session_id)

    def get_by_id_for_inventory(self, session_id: str, inventory_id: str) -> Optional[CaptureSession]:
        s = self._store.get(session_id)
        if s is None or s.inventory_id != inventory_id:
            return None
        return s

    def count_open_sessions_for_aisle(self, inventory_id: str, aisle_id: str) -> int:
        n = 0
        for s in self._store.values():
            if s.inventory_id != inventory_id or s.aisle_id != aisle_id:
                continue
            if s.closed_at is not None:
                continue
            if s.status in _TERMINAL_OPEN_BLOCK:
                continue
            n += 1
        return n

    def list_by_inventory(
        self,
        inventory_id: str,
        *,
        aisle_id: Optional[str] = None,
        statuses: Optional[Sequence[CaptureSessionStatus]] = None,
        created_from: Optional[datetime] = None,
        created_to: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 25,
    ) -> tuple[Sequence[CaptureSession], int]:
        page = max(1, page)
        page_size = max(1, page_size)
        rows = [s for s in self._store.values() if s.inventory_id == inventory_id]
        if aisle_id:
            rows = [s for s in rows if s.aisle_id == aisle_id]
        if statuses is not None and len(statuses) > 0:
            allowed = set(statuses)
            rows = [s for s in rows if s.status in allowed]
        if created_from is not None:
            rows = [s for s in rows if s.created_at >= created_from]
        if created_to is not None:
            rows = [s for s in rows if s.created_at <= created_to]
        rows.sort(key=lambda s: (s.created_at, s.id), reverse=True)
        total = len(rows)
        offset = (page - 1) * page_size
        page_rows = rows[offset : offset + page_size]
        return tuple(page_rows), total
