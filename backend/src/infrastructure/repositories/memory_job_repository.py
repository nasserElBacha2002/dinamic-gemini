"""
In-memory implementation of JobRepository — v3.0 (Épica 4).

Phase 1 corrections: claim_owner_id CAS and transactional stale reclaim (lock-emulated).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from src.application.ports.repositories import JobRepository
from src.application.services.job_claim_helpers import classify_claim_after_cas_miss
from src.application.services.job_lease_helpers import (
    classify_lease_renewal_after_cas_miss,
    classify_lease_write_after_cas_miss,
    lease_allows_finalization_write,
    lease_is_currently_valid,
)
from src.application.services.job_lease_metrics import (
    METRIC_ACQUIRE,
    METRIC_LOST,
    METRIC_REACQUIRE,
    METRIC_RENEW,
    inc_lease_metric,
)
from src.application.services.job_stale_reconciler import (
    STALE_FAILURE_CODE,
    STALE_FAILURE_MESSAGE,
    STALE_RECONCILE_STATUSES,
)
from src.domain.aisle.entities import AisleStatus
from src.domain.jobs.claim import (
    TERMINAL_JOB_STATUSES,
    JobClaimOutcome,
    JobClaimResult,
    StaleReclaimResult,
)
from src.domain.jobs.entities import Job, JobStatus
from src.domain.jobs.lease import (
    JobLease,
    LeaseRenewalOutcome,
    LeaseRenewalResult,
    LeaseWriteOutcome,
    LeaseWriteResult,
)
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
        lease_duration_seconds: int = 60,
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
                    current_lease = None
                    if job.lease_expires_at is not None and job.lease_acquired_at is not None:
                        current_lease = JobLease(
                            job_id=job_id,
                            owner_id=owner,
                            fencing_token=int(job.lease_fencing_token or 0),
                            acquired_at=job.lease_acquired_at,
                            expires_at=job.lease_expires_at,
                        )
                    return JobClaimResult(
                        outcome=JobClaimOutcome.ALREADY_OWNED,
                        job=job,
                        aisle_transition_applied=applied or aisle.status == AisleStatus.PROCESSING,
                        previous_status=JobStatus.RUNNING.value,
                        reason=classified.reason,
                        claim_owner_id=owner,
                        lease=current_lease,
                    )
                return classified

            if job.status != JobStatus.STARTING:
                return classify_claim_after_cas_miss(job, claim_owner_id=owner)

            duration = max(1, int(lease_duration_seconds or 60))
            lease_expires_at = now + timedelta(seconds=duration)
            previous = job.status.value
            job.status = JobStatus.RUNNING
            job.claim_owner_id = owner
            job.started_at = job.started_at or now
            job.last_heartbeat_at = now
            job.current_stage = "Pipeline"
            job.current_substep = "startup_confirmed"
            job.current_step_started_at = now
            job.updated_at = now
            job.lease_fencing_token = int(job.lease_fencing_token or 0) + 1
            job.lease_acquired_at = now
            job.lease_expires_at = lease_expires_at
            self._store[job.id] = job
            aisle.mark_processing(now)
            self._aisle_repo.save(aisle)
            lease = JobLease(
                job_id=job_id,
                owner_id=owner,
                fencing_token=job.lease_fencing_token,
                acquired_at=now,
                expires_at=lease_expires_at,
            )
            logger.info(
                "event=job_claim_acquired job_id=%s aisle_id=%s claim_owner_id=%s "
                "previous_status=%s new_status=running attempt=%s",
                job_id,
                aisle_id,
                owner,
                previous,
                job.attempt_count,
            )
            logger.info(
                "event=job_lease_acquired job_id=%s owner_id=%s fencing_token=%s expires_at=%s",
                job_id,
                owner,
                job.lease_fencing_token,
                lease_expires_at.isoformat(),
            )
            inc_lease_metric(METRIC_ACQUIRE, operation="claim", outcome="acquired")
            return JobClaimResult(
                outcome=JobClaimOutcome.ACQUIRED,
                job=job,
                aisle_transition_applied=True,
                previous_status=previous,
                reason="cas_acquired",
                lease=lease,
                claim_owner_id=owner,
            )

    def renew_lease(
        self,
        lease: JobLease,
        *,
        now: datetime,
        extension_seconds: int,
    ) -> LeaseRenewalResult:
        """Extend ``lease_expires_at`` under CAS (owner + fencing_token + not-yet-expired)."""
        with self._lock:
            job = self._store.get(lease.job_id)
            if not lease_is_currently_valid(
                job, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now
            ):
                result = classify_lease_renewal_after_cas_miss(
                    job, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now
                )
                logger.warning(
                    "event=job_lease_lost job_id=%s owner_id=%s fencing_token=%s outcome=%s reason=%s",
                    lease.job_id,
                    lease.owner_id,
                    lease.fencing_token,
                    result.outcome.value,
                    result.reason,
                )
                inc_lease_metric(METRIC_LOST, operation="renew", outcome=result.outcome.value)
                return result

            assert job is not None
            duration = max(1, int(extension_seconds or 0))
            new_expires_at = now + timedelta(seconds=duration)
            job.lease_expires_at = new_expires_at
            job.last_heartbeat_at = now
            job.updated_at = now
            self._store[job.id] = job
            renewed = JobLease(
                job_id=lease.job_id,
                owner_id=lease.owner_id,
                fencing_token=lease.fencing_token,
                acquired_at=lease.acquired_at,
                expires_at=new_expires_at,
            )
            logger.info(
                "event=job_lease_renewed job_id=%s owner_id=%s fencing_token=%s expires_at=%s",
                lease.job_id,
                lease.owner_id,
                lease.fencing_token,
                new_expires_at.isoformat(),
            )
            inc_lease_metric(METRIC_RENEW, operation="renew", outcome="renewed")
            return LeaseRenewalResult(outcome=LeaseRenewalOutcome.RENEWED, lease=renewed)

    def reacquire_expired_lease(
        self,
        job_id: str,
        *,
        now: datetime,
        new_owner_id: str,
        extension_seconds: int,
    ) -> JobClaimResult:
        """Steal an expired RUNNING lease: new owner + fencing_token + 1."""
        owner = (new_owner_id or "").strip()
        if not owner:
            return JobClaimResult(
                outcome=JobClaimOutcome.CONFLICT,
                reason="claim_owner_id_required",
                claim_owner_id=None,
            )
        with self._lock:
            job = self._store.get(job_id)
            if job is None:
                return JobClaimResult(
                    outcome=JobClaimOutcome.NOT_FOUND, reason="job_not_found", claim_owner_id=owner
                )
            status_value = job.status.value if isinstance(job.status, JobStatus) else str(job.status)
            if status_value in TERMINAL_JOB_STATUSES:
                return JobClaimResult(
                    outcome=JobClaimOutcome.TERMINAL,
                    job=job,
                    previous_status=status_value,
                    reason="job_terminal",
                    claim_owner_id=owner,
                )
            expired = (
                job.status == JobStatus.RUNNING
                and job.lease_expires_at is not None
                and job.lease_expires_at < now
            )
            if not expired:
                return JobClaimResult(
                    outcome=JobClaimOutcome.CONFLICT,
                    job=job,
                    previous_status=status_value,
                    reason="lease_not_expired_or_not_running",
                    claim_owner_id=owner,
                )

            duration = max(1, int(extension_seconds or 0))
            new_expires_at = now + timedelta(seconds=duration)
            job.claim_owner_id = owner
            job.lease_fencing_token = int(job.lease_fencing_token or 0) + 1
            job.lease_acquired_at = now
            job.lease_expires_at = new_expires_at
            job.last_heartbeat_at = now
            job.updated_at = now
            self._store[job.id] = job
            lease = JobLease(
                job_id=job_id,
                owner_id=owner,
                fencing_token=job.lease_fencing_token,
                acquired_at=now,
                expires_at=new_expires_at,
            )
            logger.warning(
                "event=job_lease_reacquired job_id=%s new_owner_id=%s fencing_token=%s expires_at=%s",
                job_id,
                owner,
                job.lease_fencing_token,
                new_expires_at.isoformat(),
            )
            inc_lease_metric(METRIC_REACQUIRE, operation="reacquire", outcome="acquired")
            return JobClaimResult(
                outcome=JobClaimOutcome.ACQUIRED,
                job=job,
                reason="lease_reacquired",
                claim_owner_id=owner,
                lease=lease,
            )

    def merge_result_json_if_leased(
        self,
        lease: JobLease,
        patch: dict[str, Any],
        *,
        now: datetime,
    ) -> tuple[LeaseWriteResult, Job | None]:
        """Merge ``result_json`` only while the caller still holds the lease (owner+token+not expired)."""
        with self._lock:
            job = self._store.get(lease.job_id)
            if not lease_is_currently_valid(
                job, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now
            ):
                result = classify_lease_write_after_cas_miss(
                    job, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now
                )
                logger.warning(
                    "event=job_stale_write_rejected job_id=%s owner_id=%s fencing_token=%s "
                    "outcome=%s reason=%s",
                    lease.job_id,
                    lease.owner_id,
                    lease.fencing_token,
                    result.outcome.value,
                    result.reason,
                )
                return result, job

            assert job is not None
            if patch:
                merged = dict(job.result_json or {})
                merged.update(patch)
                job.result_json = merged
                job.updated_at = now
                self._store[job.id] = job
            return LeaseWriteResult(outcome=LeaseWriteOutcome.APPLIED), job

    def touch_heartbeat_if_leased(
        self,
        lease: JobLease,
        *,
        now: datetime,
        extension_seconds: int,
    ) -> LeaseRenewalResult:
        """Renew lease + update ``last_heartbeat_at`` (same as renew for Phase 3)."""
        return self.renew_lease(lease, now=now, extension_seconds=extension_seconds)

    def assert_lease(self, lease: JobLease, *, now: datetime) -> LeaseWriteResult:
        with self._lock:
            job = self._store.get(lease.job_id)
            if lease_is_currently_valid(
                job, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now
            ):
                return LeaseWriteResult(outcome=LeaseWriteOutcome.APPLIED)
            return classify_lease_write_after_cas_miss(
                job, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now
            )

    def complete_if_leased(
        self,
        lease: JobLease,
        job: Job,
        *,
        now: datetime,
    ) -> LeaseWriteResult:
        if job.id != lease.job_id:
            return LeaseWriteResult(outcome=LeaseWriteOutcome.INVALID_STATE, reason="job_id_mismatch")
        with self._lock:
            current = self._store.get(lease.job_id)
            if not lease_is_currently_valid(
                current, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now
            ):
                result = classify_lease_write_after_cas_miss(
                    current, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now
                )
                logger.warning(
                    "event=job_stale_write_rejected job_id=%s operation=complete owner_id=%s "
                    "fencing_token=%s outcome=%s reason=%s",
                    lease.job_id,
                    lease.owner_id,
                    lease.fencing_token,
                    result.outcome.value,
                    result.reason,
                )
                return result
            # Persist caller-mutated terminal fields under the held lease.
            job.updated_at = now
            self._store[job.id] = job
            return LeaseWriteResult(outcome=LeaseWriteOutcome.APPLIED)

    def fail_if_leased(
        self,
        lease: JobLease,
        *,
        now: datetime,
        error_message: str,
        failure_code: str = "PROCESSING_FAILED",
    ) -> LeaseWriteResult:
        with self._lock:
            job = self._store.get(lease.job_id)
            if not lease_is_currently_valid(
                job, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now
            ):
                result = classify_lease_write_after_cas_miss(
                    job, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now
                )
                logger.warning(
                    "event=job_stale_write_rejected job_id=%s operation=fail owner_id=%s "
                    "fencing_token=%s outcome=%s reason=%s",
                    lease.job_id,
                    lease.owner_id,
                    lease.fencing_token,
                    result.outcome.value,
                    result.reason,
                )
                return result
            assert job is not None
            msg = error_message[:2048] if len(error_message) > 2048 else error_message
            job.status = JobStatus.FAILED
            job.updated_at = now
            job.finished_at = now
            job.last_heartbeat_at = now
            job.failure_code = failure_code
            job.failure_message = msg
            job.error_message = msg
            self._store[job.id] = job
            return LeaseWriteResult(outcome=LeaseWriteOutcome.APPLIED)

    def update_finalization_if_leased(
        self,
        lease: JobLease,
        *,
        now: datetime,
        mutator,
    ) -> LeaseWriteResult:
        """Apply finalization mutations under lease CAS."""
        with self._lock:
            current = self._store.get(lease.job_id)
            if not lease_allows_finalization_write(
                current, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now
            ):
                result = classify_lease_write_after_cas_miss(
                    current, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now
                )
                # SUCCEEDED with mismatched owner is lease_lost; with match we already returned APPLIED path.
                if current is not None and current.status == JobStatus.SUCCEEDED:
                    if not (
                        (current.claim_owner_id or "").strip() == (lease.owner_id or "").strip()
                        and int(current.lease_fencing_token or 0) == int(lease.fencing_token)
                    ):
                        result = LeaseWriteResult(
                            outcome=LeaseWriteOutcome.LEASE_LOST,
                            reason="owner_or_fencing_token_mismatch",
                        )
                logger.warning(
                    "event=job_stale_write_rejected job_id=%s operation=finalization owner_id=%s "
                    "fencing_token=%s outcome=%s reason=%s",
                    lease.job_id,
                    lease.owner_id,
                    lease.fencing_token,
                    result.outcome.value,
                    result.reason,
                )
                return result
            assert current is not None
            mutator(current)
            current.updated_at = now
            self._store[current.id] = current
            return LeaseWriteResult(outcome=LeaseWriteOutcome.APPLIED)

    def acknowledge_cancel_if_leased(
        self,
        lease: JobLease,
        *,
        now: datetime,
        reason: str,
    ) -> LeaseWriteResult:
        with self._lock:
            job = self._store.get(lease.job_id)
            if not lease_is_currently_valid(
                job, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now
            ):
                result = classify_lease_write_after_cas_miss(
                    job, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now
                )
                logger.warning(
                    "event=job_stale_write_rejected job_id=%s operation=acknowledge_cancel "
                    "owner_id=%s fencing_token=%s outcome=%s reason=%s",
                    lease.job_id,
                    lease.owner_id,
                    lease.fencing_token,
                    result.outcome.value,
                    result.reason,
                )
                return result
            assert job is not None
            msg = reason[:2048] if len(reason) > 2048 else reason
            job.status = JobStatus.CANCELED
            job.updated_at = now
            job.finished_at = now
            job.last_heartbeat_at = now
            job.failure_code = "CANCELED"
            job.failure_message = msg
            job.error_message = msg
            self._store[job.id] = job
            return LeaseWriteResult(outcome=LeaseWriteOutcome.APPLIED)

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
