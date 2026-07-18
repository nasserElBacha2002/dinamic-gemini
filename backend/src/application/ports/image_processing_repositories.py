"""Ports for Phase 2 image-processing state and attempts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from src.domain.image_processing.job_asset_processing_state import (
    JobAssetProcessingState,
    JobAssetProcessingStatus,
)
from src.domain.image_processing.processing_attempt import ProcessingAttempt


@dataclass(frozen=True)
class AssetProgressCounts:
    total: int = 0
    pending: int = 0
    processing: int = 0
    resolved: int = 0
    unrecognized: int = 0
    failed: int = 0
    manual_review: int = 0
    cancelled: int = 0


class JobAssetProcessingStateRepository(ABC):
    @abstractmethod
    def save(self, state: JobAssetProcessingState) -> None: ...

    @abstractmethod
    def get_by_job_and_asset(
        self, job_id: str, asset_id: str
    ) -> JobAssetProcessingState | None: ...

    @abstractmethod
    def list_by_job(self, job_id: str) -> Sequence[JobAssetProcessingState]: ...

    @abstractmethod
    def try_acquire(
        self,
        job_id: str,
        asset_id: str,
        *,
        expected_statuses: Sequence[JobAssetProcessingStatus],
        next_status: JobAssetProcessingStatus,
        strategy: str,
        now,
        worker_token: str | None = None,
    ) -> JobAssetProcessingState | None:
        """Atomically transition PENDING (or recoverable) → PROCESSING. None if lost race."""
        ...

    @abstractmethod
    def aggregate_progress(self, job_id: str) -> AssetProgressCounts: ...

    @abstractmethod
    def list_abandoned_processing(
        self, *, older_than, limit: int = 100
    ) -> Sequence[JobAssetProcessingState]: ...


class ProcessingAttemptRepository(ABC):
    @abstractmethod
    def save(self, attempt: ProcessingAttempt) -> None: ...

    @abstractmethod
    def get_by_id(self, attempt_id: str) -> ProcessingAttempt | None: ...

    @abstractmethod
    def get_by_unique_key(
        self,
        job_id: str,
        asset_id: str,
        strategy: str,
        attempt_number: int,
    ) -> ProcessingAttempt | None: ...

    @abstractmethod
    def list_by_job_and_asset(
        self, job_id: str, asset_id: str
    ) -> Sequence[ProcessingAttempt]: ...

    @abstractmethod
    def list_by_job(self, job_id: str) -> Sequence[ProcessingAttempt]: ...

    @abstractmethod
    def next_attempt_number(self, job_id: str, asset_id: str, strategy: str) -> int: ...
