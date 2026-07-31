"""In-memory ordered capture session repository."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from copy import deepcopy
from datetime import datetime

from src.application.errors import OrderedCaptureSessionConflictError
from src.application.ports.ordered_capture_session_repository import (
    OrderedCaptureSessionRepository,
)
from src.domain.ordered_capture.entities import (
    OrderedCaptureSession,
    OrderedCaptureSessionStatus,
)

_OPENISH = frozenset(
    {
        OrderedCaptureSessionStatus.OPEN.value,
        OrderedCaptureSessionStatus.UPLOADING.value,
    }
)


class MemoryOrderedCaptureSessionRepository(OrderedCaptureSessionRepository):
    def __init__(self) -> None:
        self._store: dict[str, OrderedCaptureSession] = {}
        self._lock = threading.Lock()

    def _open_for_aisle_unlocked(self, aisle_id: str) -> OrderedCaptureSession | None:
        rows = [
            s
            for s in self._store.values()
            if s.aisle_id == aisle_id and s.status.value in _OPENISH
        ]
        if not rows:
            return None
        return sorted(rows, key=lambda s: s.updated_at, reverse=True)[0]

    def save(self, session: OrderedCaptureSession) -> None:
        with self._lock:
            if session.status.value in _OPENISH:
                existing = self._open_for_aisle_unlocked(session.aisle_id)
                if existing is not None and existing.id != session.id:
                    raise OrderedCaptureSessionConflictError(
                        "An open ordered capture session already exists for this aisle",
                        code="ORDERED_CAPTURE_OPEN_SESSION_EXISTS",
                    )
            self._store[session.id] = deepcopy(session)

    def get_by_id(self, session_id: str) -> OrderedCaptureSession | None:
        with self._lock:
            row = self._store.get(session_id)
            return deepcopy(row) if row is not None else None

    def get_by_id_for_update(self, session_id: str) -> OrderedCaptureSession | None:
        return self.get_by_id(session_id)

    def list_by_aisle(
        self,
        aisle_id: str,
        *,
        statuses: Sequence[str] | None = None,
    ) -> list[OrderedCaptureSession]:
        with self._lock:
            rows = [s for s in self._store.values() if s.aisle_id == aisle_id]
            if statuses:
                allowed = {str(x).upper() for x in statuses}
                rows = [s for s in rows if s.status.value in allowed]
            return [deepcopy(s) for s in sorted(rows, key=lambda s: s.created_at, reverse=True)]

    def get_open_or_uploading_for_aisle(self, aisle_id: str) -> OrderedCaptureSession | None:
        with self._lock:
            existing = self._open_for_aisle_unlocked(aisle_id)
            return deepcopy(existing) if existing is not None else None

    def get_or_create_open_for_aisle(
        self, session: OrderedCaptureSession
    ) -> OrderedCaptureSession:
        with self._lock:
            existing = self._open_for_aisle_unlocked(session.aisle_id)
            if existing is not None:
                return deepcopy(existing)
            self._store[session.id] = deepcopy(session)
            return deepcopy(session)

    def transition_sealed_to_processing(
        self,
        session_id: str,
        *,
        sequence_version: int,
        job_id: str,
        now: datetime,
    ) -> OrderedCaptureSession | None:
        with self._lock:
            current = self._store.get(session_id)
            if current is None:
                return None
            if (
                current.status == OrderedCaptureSessionStatus.SEALED
                and int(current.sequence_version) == int(sequence_version)
            ):
                current.status = OrderedCaptureSessionStatus.PROCESSING
                current.processing_job_id = job_id
                current.processing_started_at = now
                current.updated_at = now
                return deepcopy(current)
            if (
                current.status == OrderedCaptureSessionStatus.PROCESSING
                and int(current.sequence_version) == int(sequence_version)
                and (current.processing_job_id or "") == job_id
            ):
                return deepcopy(current)
            if (
                current.status == OrderedCaptureSessionStatus.PROCESSING
                and int(current.sequence_version) == int(sequence_version)
                and not (current.processing_job_id or "").strip()
            ):
                current.processing_job_id = job_id
                if current.processing_started_at is None:
                    current.processing_started_at = now
                current.updated_at = now
                return deepcopy(current)
            return None
