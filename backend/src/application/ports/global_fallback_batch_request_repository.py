"""Port for GLOBAL_BATCH durable batch journal."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.domain.image_processing.global_fallback_batch_request import (
    GlobalFallbackBatchRequest,
)


class GlobalFallbackBatchRequestRepository(ABC):
    @abstractmethod
    def save(self, request: GlobalFallbackBatchRequest) -> None:
        """Insert or update by primary key."""

    @abstractmethod
    def get_by_id(self, request_id: str) -> GlobalFallbackBatchRequest | None: ...

    @abstractmethod
    def get_by_fingerprint(
        self,
        *,
        job_id: str,
        execution_id: str,
        batch_fingerprint: str,
    ) -> GlobalFallbackBatchRequest | None:
        """Lookup by unique natural key."""

    @abstractmethod
    def try_insert(self, request: GlobalFallbackBatchRequest) -> GlobalFallbackBatchRequest | None:
        """Insert if fingerprint key free; return saved row. None if conflict (caller must reload)."""

    @abstractmethod
    def list_by_job(self, job_id: str) -> Sequence[GlobalFallbackBatchRequest]: ...

    @abstractmethod
    def append_applied_operation_key(
        self,
        request_id: str,
        *,
        operation_key: str,
    ) -> bool:
        """Append idempotency key if not present. Returns False if already present."""
