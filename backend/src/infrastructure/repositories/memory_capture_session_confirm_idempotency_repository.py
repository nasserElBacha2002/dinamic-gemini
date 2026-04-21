"""In-memory CaptureSessionConfirmIdempotencyRepository (ledger only; no use case wiring yet)."""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from src.application.errors import CaptureSessionConfirmLedgerDuplicateError
from src.application.ports.capture_repositories import CaptureSessionConfirmIdempotencyRepository
from src.domain.capture.entities import CaptureSessionConfirmationLedgerEntry


class MemoryCaptureSessionConfirmIdempotencyRepository(CaptureSessionConfirmIdempotencyRepository):
    def __init__(self) -> None:
        self._store: Dict[Tuple[str, str], CaptureSessionConfirmationLedgerEntry] = {}

    def get_by_session_and_key(
        self, session_id: str, idempotency_key: str
    ) -> Optional[CaptureSessionConfirmationLedgerEntry]:
        return self._store.get((session_id, idempotency_key))

    def insert(self, entry: CaptureSessionConfirmationLedgerEntry) -> None:
        key = (entry.session_id, entry.idempotency_key)
        if key in self._store:
            raise CaptureSessionConfirmLedgerDuplicateError(
                "Duplicate capture session confirmation idempotency key for this session"
            )
        self._store[key] = entry
