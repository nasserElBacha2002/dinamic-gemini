"""In-memory JobProcessingLeaseRepository (Phase 2 corrections)."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta

from src.application.ports.image_processing_repositories import JobProcessingLeaseRepository
from src.domain.image_processing.job_processing_lease import (
    JobProcessingLease,
    JobProcessingLeaseStatus,
)

_LIVE_ACQUIRED = JobProcessingLeaseStatus.ACQUIRED


class MemoryJobProcessingLeaseRepository(JobProcessingLeaseRepository):
    def __init__(self) -> None:
        self._store: dict[tuple[str, str, str], JobProcessingLease] = {}
        self._lock = threading.Lock()

    def try_acquire_lease(
        self,
        *,
        job_id: str,
        strategy: str,
        execution_scope: str,
        worker_token: str,
        now: datetime,
        lease_duration_seconds: int,
    ) -> JobProcessingLease | None:
        key = (job_id, strategy, execution_scope)
        expires = now + timedelta(seconds=lease_duration_seconds)
        with self._lock:
            existing = self._store.get(key)
            if existing is None:
                lease = JobProcessingLease(
                    id=str(uuid.uuid4()),
                    job_id=job_id,
                    strategy=strategy,
                    execution_scope=execution_scope,
                    status=_LIVE_ACQUIRED,
                    created_at=now,
                    updated_at=now,
                    worker_token=worker_token,
                    acquired_at=now,
                    heartbeat_at=now,
                    lease_expires_at=expires,
                    version=1,
                )
                self._store[key] = lease
                return lease

            expired = (
                existing.status == _LIVE_ACQUIRED
                and existing.lease_expires_at is not None
                and existing.lease_expires_at < now
            )
            if existing.status == _LIVE_ACQUIRED and not expired:
                return None

            existing.status = _LIVE_ACQUIRED
            existing.worker_token = worker_token
            existing.acquired_at = now
            existing.heartbeat_at = now
            existing.lease_expires_at = expires
            existing.released_at = None
            existing.updated_at = now
            existing.version = int(existing.version or 1) + 1
            return existing

    def heartbeat(
        self,
        lease_id: str,
        *,
        worker_token: str,
        now: datetime,
        lease_duration_seconds: int,
    ) -> JobProcessingLease | None:
        with self._lock:
            lease = self._find_by_id(lease_id)
            if lease is None or lease.worker_token != worker_token:
                return None
            if lease.status != _LIVE_ACQUIRED:
                return None
            lease.heartbeat_at = now
            lease.lease_expires_at = now + timedelta(seconds=lease_duration_seconds)
            lease.updated_at = now
            lease.version = int(lease.version or 1) + 1
            return lease

    def release(self, lease_id: str, *, worker_token: str, now: datetime) -> None:
        with self._lock:
            lease = self._find_by_id(lease_id)
            if lease is None or lease.worker_token != worker_token:
                return
            lease.status = JobProcessingLeaseStatus.AVAILABLE
            lease.released_at = now
            lease.updated_at = now
            lease.version = int(lease.version or 1) + 1

    def complete(self, lease_id: str, *, worker_token: str, now: datetime) -> None:
        self._finish(lease_id, worker_token=worker_token, now=now, status=JobProcessingLeaseStatus.COMPLETED)

    def fail(
        self,
        lease_id: str,
        *,
        worker_token: str,
        now: datetime,
        error_message: str | None = None,
    ) -> None:
        self._finish(lease_id, worker_token=worker_token, now=now, status=JobProcessingLeaseStatus.FAILED)

    def _finish(
        self,
        lease_id: str,
        *,
        worker_token: str,
        now: datetime,
        status: JobProcessingLeaseStatus,
    ) -> None:
        with self._lock:
            lease = self._find_by_id(lease_id)
            if lease is None or lease.worker_token != worker_token:
                return
            lease.status = status
            lease.released_at = now
            lease.updated_at = now
            lease.version = int(lease.version or 1) + 1

    def get_by_job_strategy_scope(
        self, job_id: str, strategy: str, execution_scope: str
    ) -> JobProcessingLease | None:
        return self._store.get((job_id, strategy, execution_scope))

    def recover_expired(
        self, *, now: datetime, limit: int = 100
    ) -> Sequence[JobProcessingLease]:
        out: list[JobProcessingLease] = []
        with self._lock:
            for lease in self._store.values():
                if len(out) >= limit:
                    break
                if lease.status != _LIVE_ACQUIRED:
                    continue
                if lease.lease_expires_at is None or lease.lease_expires_at >= now:
                    continue
                lease.status = JobProcessingLeaseStatus.AVAILABLE
                lease.released_at = now
                lease.updated_at = now
                lease.version = int(lease.version or 1) + 1
                out.append(lease)
        return out

    def _find_by_id(self, lease_id: str) -> JobProcessingLease | None:
        for lease in self._store.values():
            if lease.id == lease_id:
                return lease
        return None
