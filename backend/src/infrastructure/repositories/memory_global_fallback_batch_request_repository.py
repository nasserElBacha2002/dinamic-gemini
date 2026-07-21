"""In-memory GLOBAL_BATCH batch journal (tests / single-process)."""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy

from src.application.ports.global_fallback_batch_request_repository import (
    GlobalFallbackBatchRequestRepository,
)
from src.domain.image_processing.global_fallback_batch_request import (
    GlobalFallbackBatchRequest,
)


class MemoryGlobalFallbackBatchRequestRepository(GlobalFallbackBatchRequestRepository):
    def __init__(self) -> None:
        self._by_id: dict[str, GlobalFallbackBatchRequest] = {}
        self._by_fp: dict[tuple[str, str, str], str] = {}

    def save(self, request: GlobalFallbackBatchRequest) -> None:
        self._by_id[request.id] = deepcopy(request)
        self._by_fp[(request.job_id, request.execution_id, request.batch_fingerprint)] = (
            request.id
        )

    def get_by_id(self, request_id: str) -> GlobalFallbackBatchRequest | None:
        row = self._by_id.get(request_id)
        return deepcopy(row) if row else None

    def get_by_fingerprint(
        self,
        *,
        job_id: str,
        execution_id: str,
        batch_fingerprint: str,
    ) -> GlobalFallbackBatchRequest | None:
        rid = self._by_fp.get((job_id, execution_id, batch_fingerprint))
        if not rid:
            return None
        return self.get_by_id(rid)

    def try_insert(self, request: GlobalFallbackBatchRequest) -> GlobalFallbackBatchRequest | None:
        key = (request.job_id, request.execution_id, request.batch_fingerprint)
        if key in self._by_fp:
            return None
        self.save(request)
        return self.get_by_id(request.id)

    def list_by_job(self, job_id: str) -> Sequence[GlobalFallbackBatchRequest]:
        rows = [deepcopy(r) for r in self._by_id.values() if r.job_id == job_id]
        rows.sort(key=lambda r: (r.batch_index, r.created_at))
        return rows

    def append_applied_operation_key(self, request_id: str, *, operation_key: str) -> bool:
        row = self._by_id.get(request_id)
        if row is None:
            return False
        if operation_key in row.applied_operation_keys:
            return False
        row.applied_operation_keys.append(operation_key)
        return True
