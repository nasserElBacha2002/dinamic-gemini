"""In-memory operational metrics source for tests / MEMORY_ONLY."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.domain.jobs.entities import JobStatus


class MemoryOperationalMetricsSource:
    def __init__(
        self,
        job_repo: Any | None,
        *,
        outbox_pending: int = 0,
        outbox_failed: int = 0,
    ) -> None:
        self._job_repo = job_repo
        self._outbox_pending = outbox_pending
        self._outbox_failed = outbox_failed

    def _iter_jobs(self) -> list[Any]:
        if self._job_repo is None:
            return []
        try:
            return list(self._job_repo.list_jobs_for_ops_scan(limit=5000))
        except NotImplementedError:
            return []
        except AttributeError:
            return []

    def count_jobs_by_status(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for job in self._iter_jobs():
            status = getattr(job, "status", None)
            key = getattr(status, "value", status)
            out[str(key)] = out.get(str(key), 0) + 1
        return out

    def count_active_leases(self) -> int:
        now = datetime.now(timezone.utc)
        n = 0
        for job in self._iter_jobs():
            status = getattr(job, "status", None)
            if status not in (
                JobStatus.RUNNING,
                JobStatus.STARTING,
                JobStatus.CANCEL_REQUESTED,
            ):
                continue
            if not getattr(job, "claim_owner_id", None) or getattr(job, "lease_expires_at", None) is None:
                continue
            exp = job.lease_expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp >= now:
                n += 1
        return n

    def count_expired_running_leases(self) -> int:
        now = datetime.now(timezone.utc)
        n = 0
        for job in self._iter_jobs():
            status = getattr(job, "status", None)
            if status not in (
                JobStatus.RUNNING,
                JobStatus.STARTING,
                JobStatus.CANCEL_REQUESTED,
            ):
                continue
            if getattr(job, "lease_expires_at", None) is None:
                continue
            exp = job.lease_expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp < now:
                n += 1
        return n

    def count_artifact_outbox(self) -> tuple[int, int]:
        return self._outbox_pending, self._outbox_failed
