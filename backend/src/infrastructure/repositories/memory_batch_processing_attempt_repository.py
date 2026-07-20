"""In-memory BatchProcessingAttemptRepository (Phase 2 corrections)."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from datetime import datetime

from src.application.ports.image_processing_repositories import (
    BatchProcessingAttemptRepository,
)
from src.domain.image_processing.batch_processing_attempt import (
    BatchProcessingAttempt,
    BatchProcessingAttemptStatus,
)


class MemoryBatchProcessingAttemptRepository(BatchProcessingAttemptRepository):
    def __init__(self) -> None:
        self._by_id: dict[str, BatchProcessingAttempt] = {}
        self._lock = threading.Lock()

    def create_started(self, attempt: BatchProcessingAttempt) -> BatchProcessingAttempt:
        with self._lock:
            self._by_id[attempt.id] = attempt
            return attempt

    def finalize(
        self,
        attempt_id: str,
        *,
        status: BatchProcessingAttemptStatus,
        now: datetime,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> BatchProcessingAttempt | None:
        with self._lock:
            attempt = self._by_id.get(attempt_id)
            if attempt is None:
                return None
            started = attempt.started_at or now
            attempt.status = status
            attempt.finished_at = now
            attempt.duration_ms = int((now - started).total_seconds() * 1000)
            attempt.error_code = error_code
            attempt.error_message = error_message
            attempt.updated_at = now
            return attempt

    def get_started_by_job(
        self, job_id: str, strategy: str, execution_scope: str
    ) -> Sequence[BatchProcessingAttempt]:
        return [
            a
            for a in self._by_id.values()
            if a.job_id == job_id
            and a.strategy == strategy
            and a.execution_scope == execution_scope
            and a.status == BatchProcessingAttemptStatus.STARTED
        ]
