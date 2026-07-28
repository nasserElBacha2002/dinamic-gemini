"""
In-memory implementation of JobRepository — v3.0 (Épica 4).

Phase 1 corrections: claim_owner_id CAS and transactional stale reclaim (lock-emulated).
"""

from __future__ import annotations

import logging
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
from src.domain.jobs.claim import JobClaimOutcome, JobClaimResult, StaleReclaimResult
from src.domain.jobs.entities import Job, JobStatus
from src.domain.jobs.stale_transition import apply_stale_failure_fields

if TYPE_CHECKING:
    from src.application.ports.repositories import AisleRepository

logger = logging.getLogger(__name__)

_AISLE_ACTIVE = frozenset({AisleStatus.QUEUED, AisleStatus.PROCESSING})
_AISLE_CLAIMABLE = frozenset(
    {AisleStatus.QUEUED, AisleStatus.ASSETS_UPLOADED, AisleStatus.PROCESSING}
)


class MemoryJobRepository(JobRepository):
    def __init__(self, aisle_repo: AisleRepository | None = None) -> None:
        self._store: dict[str, Job] = {}
        self._lock = threading.RLock()
        self._aisle_repo = aisle_repo

    def bind_aisle_repository(self, aisle_repo: AisleRepository) -> None:
        """Attach aisle repo when constructed without one (test harnesses)."""
        if self._aisle_repo is None:
            self._aisle_repo = aisle_repo

    def save(self, job: Job) -> None:
        with self._lock:
            self._store[job.id] = job

    def merge_result_json(self, job_id: str, patch: dict) -> Job | None:
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
        return candidates[: max(1, int(limit))]

    def list_jobs_for_targets(
        self,
        target_type: str,
        target_ids: Sequence[str],
        *,
        job_type: str | None = None,
    ) -> Sequence[Job]:
        if not target_ids:
            return []
        id_set = frozenset(dict.fromkeys(target_ids))
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
        claim_owner_id: str,
        aisle_id: str,
    ) -> JobClaimResult:
        owner = (claim_owner_id or "").strip()
        if not owner:
            return JobClaimResult(
                outcome=JobClaimOutcome.CONFLICT,
                reason="claim_owner_id_required",
                claim_owner_id=None,
            )
        with self._lock:
            job = self._store.get(job_id)
            if job is None:
                return JobClaimResult(outcome=JobClaimOutcome.NOT_FOUND, reason="job_not_found")

            if job.target_type != "aisle" or job.target_id != aisle_id:
                return JobClaimResult(
                    outcome=JobClaimOutcome.TARGET_MISMATCH,
                    job=job,
                    previous_status=job.status.value,
                    reason="job_aisle_mismatch",
                    claim_owner_id=owner,
                )

            if job.status in (
                JobStatus.SUCCEEDED,
                JobStatus.FAILED,
                JobStatus.CANCELED,
                JobStatus.TIMED_OUT,
            ):
                return JobClaimResult(
                    outcome=JobClaimOutcome.TERMINAL,
                    job=job,
                    previous_status=job.status.value,
                    reason="job_terminal",
                    claim_owner_id=owner,
                )

            if self._aisle_repo is None:
                return JobClaimResult(
                    outcome=JobClaimOutcome.TARGET_NOT_FOUND,
                    job=job,
                    reason="aisle_repo_unavailable",
                    claim_owner_id=owner,
                )
            aisle = self._aisle_repo.get_by_id(aisle_id)
            if aisle is None:
                return JobClaimResult(
                    outcome=JobClaimOutcome.TARGET_NOT_FOUND,
                    job=job,
                    reason="aisle_not_found",
                    claim_owner_id=owner,
                )
            if aisle.status not in _AISLE_CLAIMABLE:
                return JobClaimResult(
                    outcome=JobClaimOutcome.TARGET_INVALID_STATUS,
                    job=job,
                    previous_status=job.status.value,
                    reason=f"aisle_status:{aisle.status.value}",
                    claim_owner_id=owner,
                )

            if job.status == JobStatus.RUNNING:
                classified = classify_claim_after_cas_miss(job, claim_owner_id=owner)
                if classified.outcome == JobClaimOutcome.ALREADY_OWNED:
                    applied = False
                    if aisle.status != AisleStatus.PROCESSING:
                        aisle.mark_processing(now)
                        self._aisle_repo.save(aisle)
                        applied = True
                    return JobClaimResult(
                        outcome=JobClaimOutcome.ALREADY_OWNED,
                        job=job,
                        aisle_transition_applied=applied or aisle.status == AisleStatus.PROCESSING,
                        previous_status=JobStatus.RUNNING.value,
                        reason=classified.reason,
                        claim_owner_id=owner,
                    )
                return classified

            if job.status != JobStatus.STARTING:
                return classify_claim_after_cas_miss(job, claim_owner_id=owner)

            previous = job.status.value
            job.status = JobStatus.RUNNING
            job.claim_owner_id = owner
            job.started_at = job.started_at or now
            job.last_heartbeat_at = now
            job.current_stage = "Pipeline"
            job.current_substep = "startup_confirmed"
            job.current_step_started_at = now
            job.updated_at = now
            self._store[job.id] = job
            aisle.mark_processing(now)
            self._aisle_repo.save(aisle)
            logger.info(
                "event=job_claim_acquired job_id=%s aisle_id=%s claim_owner_id=%s "
                "previous_status=%s new_status=running attempt=%s",
                job_id,
                aisle_id,
                owner,
                previous,
                job.attempt_count,
            )
            return JobClaimResult(
                outcome=JobClaimOutcome.ACQUIRED,
                job=job,
                aisle_transition_applied=True,
                previous_status=previous,
                reason="cas_acquired",
                claim_owner_id=owner,
            )

    def try_reclaim_stale_job_and_reconcile_aisle(
        self,
        job_id: str,
        *,
        now: datetime,
        stale_after_seconds: int,
    ) -> StaleReclaimResult:
        if stale_after_seconds <= 0:
            return StaleReclaimResult(won=False, reason="stale_disabled")
        with self._lock:
            job = self._store.get(job_id)
            if job is None or job.status not in STALE_RECONCILE_STATUSES:
                return StaleReclaimResult(won=False, job=job, reason="not_eligible")
            reference = job.last_heartbeat_at or job.updated_at
            if (now - reference).total_seconds() < stale_after_seconds:
                return StaleReclaimResult(won=False, job=job, reason="not_stale")

            apply_stale_failure_fields(job, now=now)
            self._store[job.id] = job

            aisle_applied = False
            if (
                self._aisle_repo is not None
                and job.target_type == "aisle"
                and job.target_id
            ):
                other_active = [
                    j
                    for j in self._store.values()
                    if j.id != job_id
                    and j.target_type == "aisle"
                    and j.target_id == job.target_id
                    and j.status in STALE_RECONCILE_STATUSES
                ]
                aisle = self._aisle_repo.get_by_id(job.target_id)
                if aisle is not None and aisle.status in _AISLE_ACTIVE and not other_active:
                    aisle.mark_failed(
                        now,
                        error_code=STALE_FAILURE_CODE,
                        error_message=STALE_FAILURE_MESSAGE,
                        retryable=True,
                    )
                    self._aisle_repo.save(aisle)
                    aisle_applied = True
                elif other_active:
                    logger.warning(
                        "event=job_aisle_state_inconsistency job_id=%s aisle_id=%s "
                        "job_status=failed aisle_status=%s processing_job_id=%s",
                        job_id,
                        job.target_id,
                        aisle.status.value if aisle else None,
                        other_active[0].id,
                    )

            logger.warning(
                "event=job_stale_reclaimed job_id=%s aisle_id=%s previous_owner=%s "
                "new_status=failed attempt=%s",
                job_id,
                job.target_id if job.target_type == "aisle" else None,
                job.claim_owner_id,
                job.attempt_count,
            )
            return StaleReclaimResult(
                won=True,
                job=job,
                aisle_transition_applied=aisle_applied,
                reason="stale_reclaimed",
            )

    def reclaim_stale_running_jobs(
        self, stale_after_seconds: int, *, batch_size: int = 100
    ) -> int:
        if stale_after_seconds <= 0:
            return 0
        now = datetime.now(timezone.utc)
        batch = max(1, min(int(batch_size), 500))
        with self._lock:
            candidates = [
                j
                for j in self._store.values()
                if j.status in STALE_RECONCILE_STATUSES
                and (now - (j.last_heartbeat_at or j.updated_at)).total_seconds()
                >= stale_after_seconds
            ]
            candidates.sort(
                key=lambda j: (j.last_heartbeat_at or j.updated_at, j.id)
            )
            ids = [j.id for j in candidates[:batch]]
        reclaimed = 0
        for job_id in ids:
            result = self.try_reclaim_stale_job_and_reconcile_aisle(
                job_id, now=now, stale_after_seconds=stale_after_seconds
            )
            if result.won:
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
