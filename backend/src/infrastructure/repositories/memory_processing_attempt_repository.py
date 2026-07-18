"""In-memory ProcessingAttemptRepository (Phase 2 corrections)."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Sequence
from datetime import datetime

from src.application.ports.image_processing_repositories import ProcessingAttemptRepository
from src.domain.image_processing.processing_attempt import (
    ProcessingAttempt,
    ProcessingAttemptStatus,
)


class MemoryProcessingAttemptRepository(ProcessingAttemptRepository):
    def __init__(self) -> None:
        self._by_id: dict[str, ProcessingAttempt] = {}
        self._by_key: dict[tuple[str, str, str, int], ProcessingAttempt] = {}
        self._lock = threading.Lock()

    def save(self, attempt: ProcessingAttempt) -> None:
        with self._lock:
            self._by_id[attempt.id] = attempt
            self._by_key[
                (attempt.job_id, attempt.asset_id, attempt.strategy, attempt.attempt_number)
            ] = attempt

    def get_by_id(self, attempt_id: str) -> ProcessingAttempt | None:
        return self._by_id.get(attempt_id)

    def get_by_unique_key(
        self,
        job_id: str,
        asset_id: str,
        strategy: str,
        attempt_number: int,
    ) -> ProcessingAttempt | None:
        return self._by_key.get((job_id, asset_id, strategy, attempt_number))

    def list_by_job_and_asset(
        self, job_id: str, asset_id: str
    ) -> Sequence[ProcessingAttempt]:
        rows = [
            a
            for a in self._by_id.values()
            if a.job_id == job_id and a.asset_id == asset_id
        ]
        rows.sort(key=lambda a: (a.attempt_number, a.created_at))
        return rows

    def list_by_job(self, job_id: str) -> Sequence[ProcessingAttempt]:
        rows = [a for a in self._by_id.values() if a.job_id == job_id]
        rows.sort(key=lambda a: (a.asset_id, a.attempt_number, a.created_at))
        return rows

    def next_attempt_number(self, job_id: str, asset_id: str, strategy: str) -> int:
        numbers = [
            a.attempt_number
            for a in self._by_id.values()
            if a.job_id == job_id and a.asset_id == asset_id and a.strategy == strategy
        ]
        return (max(numbers) + 1) if numbers else 1

    def create_next_attempt(
        self,
        *,
        job_id: str,
        asset_id: str,
        strategy: str,
        status: ProcessingAttemptStatus,
        now: datetime,
        provider: str | None = None,
        model: str | None = None,
        execution_scope: str | None = None,
        configuration_snapshot_version: int | None = None,
        parent_batch_attempt_id: str | None = None,
        batch_execution_id: str | None = None,
        worker_token: str | None = None,
        logical_asset_attempt: bool = True,
    ) -> ProcessingAttempt:
        with self._lock:
            number = self.next_attempt_number(job_id, asset_id, strategy)
            attempt = ProcessingAttempt(
                id=str(uuid.uuid4()),
                job_id=job_id,
                asset_id=asset_id,
                strategy=strategy,
                attempt_number=number,
                status=status,
                created_at=now,
                provider=provider,
                model=model,
                started_at=now,
                execution_scope=execution_scope,
                logical_asset_attempt=logical_asset_attempt,
                configuration_snapshot_version=configuration_snapshot_version,
                parent_batch_attempt_id=parent_batch_attempt_id,
                batch_execution_id=batch_execution_id,
                worker_token=worker_token,
                updated_at=now,
            )
            self._by_id[attempt.id] = attempt
            self._by_key[(job_id, asset_id, strategy, number)] = attempt
            return attempt

    def list_started_by_job(self, job_id: str) -> Sequence[ProcessingAttempt]:
        return [
            a
            for a in self._by_id.values()
            if a.job_id == job_id and a.status == ProcessingAttemptStatus.STARTED
        ]
