"""In-memory ExternalImageAnalysisRequestRepository (tests / single-process)."""

from __future__ import annotations

from collections.abc import Sequence
from threading import Lock

from src.application.ports.external_image_analysis_request_repository import (
    ExternalImageAnalysisRequestRepository,
)
from src.domain.image_processing.external_image_analysis_request import (
    ExternalImageAnalysisRequest,
    ExternalRequestStatus,
)


class MemoryExternalImageAnalysisRequestRepository(ExternalImageAnalysisRequestRepository):
    def __init__(self) -> None:
        self._by_id: dict[str, ExternalImageAnalysisRequest] = {}
        self._by_key: dict[str, str] = {}
        self._lock = Lock()

    def save(self, request: ExternalImageAnalysisRequest) -> None:
        with self._lock:
            self._by_id[request.id] = request
            self._by_key[request.idempotency_key] = request.id

    def get_by_id(self, request_id: str) -> ExternalImageAnalysisRequest | None:
        with self._lock:
            return self._by_id.get(request_id)

    def get_by_idempotency_key(
        self, idempotency_key: str
    ) -> ExternalImageAnalysisRequest | None:
        with self._lock:
            rid = self._by_key.get(idempotency_key)
            return self._by_id.get(rid) if rid else None

    def try_claim(
        self, *, request: ExternalImageAnalysisRequest
    ) -> ExternalImageAnalysisRequest:
        with self._lock:
            existing_id = self._by_key.get(request.idempotency_key)
            if existing_id is not None:
                return self._by_id[existing_id]
            self._by_id[request.id] = request
            self._by_key[request.idempotency_key] = request.id
            return request

    def list_by_job(self, job_id: str) -> Sequence[ExternalImageAnalysisRequest]:
        with self._lock:
            return [r for r in self._by_id.values() if r.job_id == job_id]

    def list_by_job_and_asset(
        self, job_id: str, asset_id: str
    ) -> Sequence[ExternalImageAnalysisRequest]:
        with self._lock:
            return [
                r
                for r in self._by_id.values()
                if r.job_id == job_id and r.asset_id == asset_id
            ]

    def count_by_job_statuses(
        self, job_id: str, statuses: Sequence[ExternalRequestStatus]
    ) -> int:
        wanted = {s for s in statuses}
        with self._lock:
            return sum(
                1
                for r in self._by_id.values()
                if r.job_id == job_id and r.status in wanted
            )


__all__ = ["MemoryExternalImageAnalysisRequestRepository"]
