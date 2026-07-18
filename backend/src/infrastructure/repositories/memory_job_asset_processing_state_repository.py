"""In-memory JobAssetProcessingStateRepository (Phase 2 corrections)."""

from __future__ import annotations

import dataclasses
import threading
from collections.abc import Sequence
from datetime import datetime

from src.application.errors import AssetProcessingStateConcurrencyError
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
        self._lock = threading.Lock()

    def save(self, state: JobAssetProcessingState) -> None:
        with self._lock:
            self._store[(state.job_id, state.asset_id)] = dataclasses.replace(state)

    def get_by_job_and_asset(
        self, job_id: str, asset_id: str
    ) -> JobAssetProcessingState | None:
        with self._lock:
            state = self._store.get((job_id, asset_id))
            return dataclasses.replace(state) if state is not None else None

    def list_by_job(self, job_id: str) -> Sequence[JobAssetProcessingState]:
        with self._lock:
            return [
                dataclasses.replace(s) for (jid, _), s in self._store.items() if jid == job_id
            ]

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
        with self._lock:
            state = self._store.get((job_id, asset_id))
            if state is None or state.status not in expected_statuses:
                return None
            state.status = next_status
            state.last_strategy = strategy
            state.started_at = now
            state.updated_at = now
            state.version = int(state.version or 1) + 1
            state.worker_token = worker_token
            self._store[(job_id, asset_id)] = state
            return dataclasses.replace(state)

    def save_with_ownership(
        self,
        state: JobAssetProcessingState,
        *,
        expected_version: int,
        worker_token: str | None,
    ) -> None:
        with self._lock:
            current = self._store.get((state.job_id, state.asset_id))
            if (
                current is None
                or int(current.version or 1) != int(expected_version)
                or (worker_token is not None and current.worker_token != worker_token)
            ):
                raise AssetProcessingStateConcurrencyError(
                    f"job_asset_processing_states ownership conflict "
                    f"job_id={state.job_id} asset_id={state.asset_id} "
                    f"expected_version={expected_version} worker_token={worker_token}"
                )
            self._store[(state.job_id, state.asset_id)] = dataclasses.replace(state)

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
        self,
        *,
        older_than: datetime,
        limit: int = 100,
        job_id: str | None = None,
        as_of: datetime | None = None,
    ) -> Sequence[JobAssetProcessingState]:
        lease_cutoff = as_of if as_of is not None else older_than
        with self._lock:
            out: list[JobAssetProcessingState] = []
            for s in self._store.values():
                if s.status != JobAssetProcessingStatus.PROCESSING:
                    continue
                if job_id is not None and s.job_id != job_id:
                    continue
                if s.lease_expires_at is not None:
                    if s.lease_expires_at >= lease_cutoff:
                        continue
                else:
                    ref = s.updated_at or s.started_at
                    if ref is None or ref >= older_than:
                        continue
                out.append(dataclasses.replace(s))
                if len(out) >= limit:
                    break
            return out
