"""Port for Phase 7 processing_events persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.domain.image_processing.processing_event import ProcessingEvent


class ProcessingEventRepository(ABC):
    @abstractmethod
    def append(self, event: ProcessingEvent) -> None: ...

    @abstractmethod
    def list_by_job_asset(
        self,
        job_id: str,
        asset_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[ProcessingEvent]: ...

    @abstractmethod
    def count_by_job_asset(self, job_id: str, asset_id: str) -> int: ...

    @abstractmethod
    def list_by_job(
        self,
        job_id: str,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> Sequence[ProcessingEvent]: ...


__all__ = ["ProcessingEventRepository"]
