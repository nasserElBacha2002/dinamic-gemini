"""
In-memory implementation of JobRepository — v3.0 (Épica 4).

Used when no database is configured or when SQL fallback is used.
get_latest_by_target orders by updated_at DESC, then created_at DESC.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.application.ports.repositories import JobRepository
from src.domain.jobs.entities import Job, JobStatus


class MemoryJobRepository(JobRepository):
    def __init__(self) -> None:
        self._store: dict[str, Job] = {}

    def save(self, job: Job) -> None:
        self._store[job.id] = job

    def merge_result_json(self, job_id: str, patch: dict) -> Job | None:
        """Thread-safe merge of top-level ``result_json`` keys (Phase 2 asset_progress)."""
        job = self._store.get(job_id)
        if job is None:
            return None
        merged = dict(job.result_json or {})
        merged.update(patch)
        job.result_json = merged
        self._store[job_id] = job
        return job

    def get_by_id(self, job_id: str) -> Job | None:
        return self._store.get(job_id)

    def get_latest_by_target(self, target_type: str, target_id: str) -> Job | None:
        candidates = [
            j
            for j in self._store.values()
            if j.target_type == target_type and j.target_id == target_id
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda j: (j.updated_at, j.created_at), reverse=True)
        return candidates[0]

    def list_jobs_for_target(
        self, target_type: str, target_id: str, *, limit: int = 50
    ) -> Sequence[Job]:
        candidates = [
            j
            for j in self._store.values()
            if j.target_type == target_type and j.target_id == target_id
        ]
        candidates.sort(key=lambda j: (j.updated_at, j.created_at), reverse=True)
        n = max(1, int(limit))
        return candidates[:n]

    def list_jobs_for_targets(
        self,
        target_type: str,
        target_ids: Sequence[str],
        *,
        job_type: str | None = None,
    ) -> Sequence[Job]:
        """All matching jobs for targets (no per-target history cap)."""
        if not target_ids:
            return []
        unique_ids = list(dict.fromkeys(target_ids))
        id_set = frozenset(unique_ids)
        candidates = [
            j
            for j in self._store.values()
            if j.target_type == target_type
            and j.target_id in id_set
            and (job_type is None or j.job_type == job_type)
        ]
        candidates.sort(key=lambda j: (j.target_id, j.updated_at, j.created_at), reverse=True)
        out: list[Job] = []
        seen: set[str] = set()
        for job in candidates:
            if job.id in seen:
                continue
            seen.add(job.id)
            out.append(job)
        return out

    def list_all_jobs(self) -> Sequence[Job]:
        return list(self._store.values())

    def claim_next_queued_job(self) -> Job | None:
        candidates = [j for j in self._store.values() if j.status == JobStatus.QUEUED]
        if not candidates:
            return None
        candidates.sort(key=lambda j: (j.created_at, j.id))
        return candidates[0]

    def get_latest_by_targets(self, target_type: str, target_ids: Sequence[str]) -> dict[str, Job]:
        if not target_ids:
            return {}
        id_set = frozenset(target_ids)
        by_target: dict[str, Job] = {}
        for j in self._store.values():
            if j.target_type != target_type or j.target_id not in id_set:
                continue
            existing = by_target.get(j.target_id)
            if existing is None or (j.updated_at, j.created_at) > (
                existing.updated_at,
                existing.created_at,
            ):
                by_target[j.target_id] = j
        return by_target
