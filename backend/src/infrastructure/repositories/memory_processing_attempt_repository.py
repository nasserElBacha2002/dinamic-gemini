"""In-memory ProcessingAttemptRepository (Phase 2)."""

from __future__ import annotations

from collections.abc import Sequence

from src.application.ports.image_processing_repositories import ProcessingAttemptRepository
from src.domain.image_processing.processing_attempt import ProcessingAttempt


class MemoryProcessingAttemptRepository(ProcessingAttemptRepository):
    def __init__(self) -> None:
        self._by_id: dict[str, ProcessingAttempt] = {}
        self._by_key: dict[tuple[str, str, str, int], ProcessingAttempt] = {}

    def save(self, attempt: ProcessingAttempt) -> None:
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
