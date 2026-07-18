"""In-memory JobAssetProcessingStateRepository (Phase 2)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from src.application.ports.image_processing_repositories import (
    AssetProgressCounts,
    JobAssetProcessingStateRepository,
)
from src.domain.image_processing.job_asset_processing_state import (
    JobAssetProcessingState,
    JobAssetProcessingStatus,
)


class MemoryJobAssetProcessingStateRepository(JobAssetProcessingStateRepository):
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], JobAssetProcessingState] = {}

    def save(self, state: JobAssetProcessingState) -> None:
        self._store[(state.job_id, state.asset_id)] = state

    def get_by_job_and_asset(
        self, job_id: str, asset_id: str
    ) -> JobAssetProcessingState | None:
        return self._store.get((job_id, asset_id))

    def list_by_job(self, job_id: str) -> Sequence[JobAssetProcessingState]:
        return [s for (jid, _), s in self._store.items() if jid == job_id]

    def try_acquire(
        self,
        job_id: str,
        asset_id: str,
        *,
        expected_statuses: Sequence[JobAssetProcessingStatus],
        next_status: JobAssetProcessingStatus,
        strategy: str,
        now: datetime,
        worker_token: str | None = None,
    ) -> JobAssetProcessingState | None:
        state = self._store.get((job_id, asset_id))
        if state is None or state.status not in expected_statuses:
            return None
        state.status = next_status
        state.last_strategy = strategy
        state.started_at = now
        state.updated_at = now
        state.version = int(state.version or 1) + 1
        self._store[(job_id, asset_id)] = state
        return state

    def aggregate_progress(self, job_id: str) -> AssetProgressCounts:
        rows = self.list_by_job(job_id)
        pending = processing = resolved = unrecognized = failed = manual = cancelled = 0
        for s in rows:
            if s.status == JobAssetProcessingStatus.PENDING:
                pending += 1
            elif s.status == JobAssetProcessingStatus.PROCESSING:
                processing += 1
            elif s.status == JobAssetProcessingStatus.RESOLVED:
                resolved += 1
            elif s.status == JobAssetProcessingStatus.UNRECOGNIZED:
                unrecognized += 1
            elif s.status == JobAssetProcessingStatus.FAILED_TECHNICAL:
                failed += 1
            elif s.status == JobAssetProcessingStatus.PENDING_MANUAL_REVIEW:
                manual += 1
            elif s.status == JobAssetProcessingStatus.CANCELLED:
                cancelled += 1
        return AssetProgressCounts(
            total=len(rows),
            pending=pending,
            processing=processing,
            resolved=resolved,
            unrecognized=unrecognized,
            failed=failed,
            manual_review=manual,
            cancelled=cancelled,
        )

    def list_abandoned_processing(
        self, *, older_than: datetime, limit: int = 100
    ) -> Sequence[JobAssetProcessingState]:
        out: list[JobAssetProcessingState] = []
        for s in self._store.values():
            if s.status != JobAssetProcessingStatus.PROCESSING:
                continue
            ref = s.updated_at or s.started_at
            if ref is not None and ref < older_than:
                out.append(s)
            if len(out) >= limit:
                break
        return out
