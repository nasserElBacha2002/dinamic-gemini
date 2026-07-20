"""In-memory ProcessingActionIdempotencyRepository."""

from __future__ import annotations

import threading
from copy import deepcopy

from src.application.errors import IdempotencyKeyReusedError
from src.application.ports.processing_action_idempotency_repository import (
    ProcessingActionIdempotencyRepository,
)
from src.domain.image_processing.processing_action_idempotency import (
    ProcessingActionIdempotencyRecord,
)


class MemoryProcessingActionIdempotencyRepository(ProcessingActionIdempotencyRepository):
    def __init__(self) -> None:
        self._rows: dict[tuple[str, str, str, str], ProcessingActionIdempotencyRecord] = {}
        self._lock = threading.Lock()

    def get(
        self,
        *,
        action_type: str,
        job_id: str,
        asset_id: str,
        idempotency_key: str,
    ) -> ProcessingActionIdempotencyRecord | None:
        with self._lock:
            row = self._rows.get((action_type, job_id, asset_id, idempotency_key))
            return deepcopy(row) if row else None

    def insert(self, record: ProcessingActionIdempotencyRecord) -> None:
        key = (
            record.action_type,
            record.job_id,
            record.asset_id,
            record.idempotency_key,
        )
        with self._lock:
            if key in self._rows:
                raise IdempotencyKeyReusedError(
                    "IDEMPOTENCY_KEY_REUSED: key already registered with a different payload"
                )
            self._rows[key] = deepcopy(record)

    def update_response(self, record: ProcessingActionIdempotencyRecord) -> None:
        key = (
            record.action_type,
            record.job_id,
            record.asset_id,
            record.idempotency_key,
        )
        with self._lock:
            self._rows[key] = deepcopy(record)


__all__ = ["MemoryProcessingActionIdempotencyRepository"]
