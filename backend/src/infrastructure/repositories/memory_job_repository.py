"""
In-memory implementation of JobRepository — v3.0 (Épica 4).

Used when no database is configured or when SQL fallback is used.
get_latest_by_target orders by updated_at DESC, then created_at DESC.

Phase 1: claim/reclaim use an internal lock to emulate SQL atomicity for tests.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from src.application.ports.repositories import JobRepository
from src.application.services.job_claim_helpers import classify_claim_after_cas_miss
from src.application.services.job_stale_reconciler import (
    STALE_FAILURE_CODE,
    STALE_FAILURE_MESSAGE,
    STALE_RECONCILE_STATUSES,
)
from src.domain.aisle.entities import AisleStatus
from src.domain.jobs.claim import JobClaimOutcome, JobClaimResult
from src.domain.jobs.entities import Job, JobStatus
from src.domain.jobs.finalization import FinalizationStatus

if TYPE_CHECKING:
    from src.application.ports.repositories import AisleRepository

_AISLE_ACTIVE = frozenset({AisleStatus.QUEUED, AisleStatus.PROCESSING})


class MemoryJobRepository(JobRepository):
    def __init__(self, aisle_repo: AisleRepository | None = None) -> None:
        self._store: dict[str, Job] = {}
        self._lock = threading.RLock()
        self._aisle_repo = aisle_repo

    def save(self, job: Job) -> None:
        with self._lock:
            self._store[job.id] = job

    def merge_result_json(self, job_id: str, patch: dict) -> Job | None:
        """Thread-safe merge of top-level ``result_json`` keys (Phase 2 asset_progress)."""
        with self._lock:
            job = self._store.get(job_id)
            if job is None:
                return None
            merged = dict(job.result_json or {})
            merged.update(patch)
            job.result_json = merged
            self._store[job_id] = job
            return job

    def get_by_id(self, job_id: str) -> Job | None:
        with self._lock:
            return self._store.get(job_id)

    def get_latest_by_target(self, target_type: str, target_id: str) -> Job | None:
        with self._lock:
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
        with self._lock:
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
        with self._lock:
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
        with self._lock:
            return list(self._store.values())

    def claim_next_queued_job(self) -> Job | None:
        """Atomically claim oldest QUEUED → STARTING (mirrors SQL UPDLOCK claim)."""
        with self._lock:
            candidates = [j for j in self._store.values() if j.status == JobStatus.QUEUED]
            if not candidates:
                return None
            candidates.sort(key=lambda j: (j.created_at, j.id))
            job = candidates[0]
            now = datetime.now(timezone.utc)
            job.status = JobStatus.STARTING
            job.started_at = job.started_at or now
            job.updated_at = now
            self._store[job.id] = job
            return job

    def try_claim_starting_to_running(
        self,
        job_id: str,
        *,
        now: datetime,
        execution_id: str | None = None,
        aisle_id: str | None = None,
    ) -> JobClaimResult:
        with self._lock:
            job = self._store.get(job_id)
            if job is None:
                return JobClaimResult(outcome=JobClaimOutcome.NOT_FOUND, reason="job_not_found")

            if job.status == JobStatus.RUNNING:
                result = classify_claim_after_cas_miss(job, execution_id=execution_id)
                if result.outcome == JobClaimOutcome.ALREADY_OWNED:
                    aisle = self._reconcile_aisle_processing(aisle_id, now)
                    return JobClaimResult(
                        outcome=JobClaimOutcome.ALREADY_OWNED,
                        job=job,
                        aisle=aisle,
                        previous_status=JobStatus.RUNNING.value,
                        reason=result.reason,
                    )
                return result

            if job.status != JobStatus.STARTING:
                return classify_claim_after_cas_miss(job, execution_id=execution_id)

            # CAS: only STARTING may become RUNNING.
            previous = job.status.value
            job.status = JobStatus.RUNNING
            job.started_at = job.started_at or now
            job.last_heartbeat_at = now
            job.current_stage = "Pipeline"
            job.current_substep = "startup_confirmed"
            job.current_step_started_at = now
            job.updated_at = now
            # Do not bump attempt_count — set once at job creation for a new attempt.
            self._store[job.id] = job
            aisle = self._reconcile_aisle_processing(aisle_id, now)
            return JobClaimResult(
                outcome=JobClaimOutcome.ACQUIRED,
                job=job,
                aisle=aisle,
                previous_status=previous,
                reason="cas_acquired",
            )

    def try_fail_stale_job(
        self,
        job_id: str,
        *,
        now: datetime,
        stale_after_seconds: int,
    ) -> bool:
        if stale_after_seconds <= 0:
            return False
        with self._lock:
            job = self._store.get(job_id)
            if job is None or job.status not in STALE_RECONCILE_STATUSES:
                return False
            reference = job.last_heartbeat_at or job.updated_at
            if (now - reference).total_seconds() < stale_after_seconds:
                return False
            job.status = JobStatus.FAILED
            job.failure_code = STALE_FAILURE_CODE
            job.failure_message = STALE_FAILURE_MESSAGE
            job.error_message = STALE_FAILURE_MESSAGE
            job.finished_at = now
            job.updated_at = now
            if job.finalization_status in (
                FinalizationStatus.IN_PROGRESS,
                FinalizationStatus.NOT_STARTED,
            ):
                job.finalization_status = FinalizationStatus.FAILED
                if job.finalization_error_code is None:
                    job.finalization_error_code = STALE_FAILURE_CODE
                if job.finalization_started_at is None:
                    job.finalization_started_at = now
            self._store[job.id] = job
            return True

    def reclaim_stale_running_jobs(self, stale_after_seconds: int) -> int:
        if stale_after_seconds <= 0:
            return 0
        now = datetime.now(timezone.utc)
        with self._lock:
            candidates = [
                j.id
                for j in self._store.values()
                if j.status in STALE_RECONCILE_STATUSES
                and (now - (j.last_heartbeat_at or j.updated_at)).total_seconds()
                >= stale_after_seconds
            ]
        reclaimed = 0
        for job_id in candidates:
            if self.try_fail_stale_job(
                job_id, now=now, stale_after_seconds=stale_after_seconds
            ):
                self._reconcile_aisle_after_stale(job_id, now=now)
                reclaimed += 1
        return reclaimed

    def get_latest_by_targets(self, target_type: str, target_ids: Sequence[str]) -> dict[str, Job]:
        if not target_ids:
            return {}
        id_set = frozenset(target_ids)
        by_target: dict[str, Job] = {}
        with self._lock:
            jobs = list(self._store.values())
        for j in jobs:
            if j.target_type != target_type or j.target_id not in id_set:
                continue
            existing = by_target.get(j.target_id)
            if existing is None or (j.updated_at, j.created_at) > (
                existing.updated_at,
                existing.created_at,
            ):
                by_target[j.target_id] = j
        return by_target

    def _reconcile_aisle_processing(self, aisle_id: str | None, now: datetime):
        if not aisle_id or self._aisle_repo is None:
            return None
        aisle = self._aisle_repo.get_by_id(aisle_id)
        if aisle is None:
            return None
        if aisle.status in (AisleStatus.QUEUED, AisleStatus.ASSETS_UPLOADED, AisleStatus.PROCESSING):
            aisle.mark_processing(now)
            self._aisle_repo.save(aisle)
        return aisle

    def _reconcile_aisle_after_stale(self, job_id: str, *, now: datetime) -> None:
        if self._aisle_repo is None:
            return
        job = self.get_by_id(job_id)
        if job is None or job.target_type != "aisle" or not job.target_id:
            return
        aisle = self._aisle_repo.get_by_id(job.target_id)
        if aisle is None or aisle.status not in _AISLE_ACTIVE:
            return
        # Do not fail aisle if another active job still owns it.
        with self._lock:
            other_active = [
                j
                for j in self._store.values()
                if j.id != job_id
                and j.target_type == "aisle"
                and j.target_id == job.target_id
                and j.status in STALE_RECONCILE_STATUSES
            ]
        if other_active:
            return
        aisle.mark_failed(
            now,
            error_code=STALE_FAILURE_CODE,
            error_message=STALE_FAILURE_MESSAGE,
            retryable=True,
        )
        self._aisle_repo.save(aisle)
