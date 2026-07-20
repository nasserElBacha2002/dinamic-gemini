"""In-memory ProcessingEventRepository (Phase 7)."""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy

from src.application.ports.processing_event_repository import ProcessingEventRepository
from src.domain.image_processing.processing_event import ProcessingEvent


class MemoryProcessingEventRepository(ProcessingEventRepository):
    def __init__(self) -> None:
        self._rows: list[ProcessingEvent] = []

    def append(self, event: ProcessingEvent) -> None:
        self._rows.append(deepcopy(event))

    def list_by_job_asset(
        self,
        job_id: str,
        asset_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[ProcessingEvent]:
        matched = [
            deepcopy(e)
            for e in self._rows
            if e.job_id == job_id and e.asset_id == asset_id
        ]
        matched.sort(key=lambda e: e.created_at)
        return matched[offset : offset + limit]

    def count_by_job_asset(self, job_id: str, asset_id: str) -> int:
        return sum(1 for e in self._rows if e.job_id == job_id and e.asset_id == asset_id)

    def list_by_job(
        self,
        job_id: str,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> Sequence[ProcessingEvent]:
        matched = [deepcopy(e) for e in self._rows if e.job_id == job_id]
        matched.sort(key=lambda e: e.created_at)
        return matched[offset : offset + limit]


__all__ = ["MemoryProcessingEventRepository"]
