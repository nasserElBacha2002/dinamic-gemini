"""Port for durable external image-analysis request claims."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.domain.image_processing.external_image_analysis_request import (
    ExternalImageAnalysisRequest,
    ExternalRequestStatus,
)


class ExternalImageAnalysisRequestRepository(ABC):
    @abstractmethod
    def save(self, request: ExternalImageAnalysisRequest) -> None: ...

    @abstractmethod
    def get_by_id(self, request_id: str) -> ExternalImageAnalysisRequest | None: ...

    @abstractmethod
    def get_by_idempotency_key(
        self, idempotency_key: str
    ) -> ExternalImageAnalysisRequest | None: ...

    @abstractmethod
    def try_claim(
        self,
        *,
        request: ExternalImageAnalysisRequest,
    ) -> ExternalImageAnalysisRequest:
        """Insert claim if key is free; otherwise return the existing row (atomic)."""
        ...

    @abstractmethod
    def list_by_job(self, job_id: str) -> Sequence[ExternalImageAnalysisRequest]: ...

    @abstractmethod
    def list_by_job_and_asset(
        self, job_id: str, asset_id: str
    ) -> Sequence[ExternalImageAnalysisRequest]: ...

    @abstractmethod
    def count_by_job_statuses(
        self, job_id: str, statuses: Sequence[ExternalRequestStatus]
    ) -> int: ...


__all__ = ["ExternalImageAnalysisRequestRepository"]
