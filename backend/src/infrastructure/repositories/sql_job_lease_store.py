"""SQL Server job-lease CAS operations (Phase 6 extract).

Internal collaborator for ``SqlJobRepository`` — keeps lease-gated UPDATE predicates
identical across fence SELECT and terminal writes.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from src.application.services.job_lease_helpers import (
    classify_lease_renewal_after_cas_miss,
    classify_lease_write_after_cas_miss,
    lease_allows_finalization_write,
    lease_is_currently_valid,
)
from src.database.sqlserver import SqlServerClient
from src.domain.jobs.claim import TERMINAL_JOB_STATUSES, JobClaimOutcome, JobClaimResult
from src.domain.jobs.entities import Job, JobStatus
from src.domain.jobs.lease import (
    JobLease,
    LeaseRenewalOutcome,
    LeaseRenewalResult,
    LeaseWriteOutcome,
    LeaseWriteResult,
)
from src.infrastructure.repositories.db_row_text import normalize_db_str
from src.infrastructure.repositories.sql_job_lease_predicates import (
    LEASE_ACTIVE_PREDICATE_SQL,
    lease_active_bind_params,
)
from src.infrastructure.repositories.sql_job_row_mapper import ensure_utc as _ensure_utc
from src.infrastructure.repositories.sql_job_row_mapper import parse_json as _parse_json

logger = logging.getLogger(__name__)


class SqlJobLeaseStore:
    """Lease acquire/renew/assert/complete/fail SQL — used by ``SqlJobRepository``."""

    def __init__(
        self,
        client: SqlServerClient,
        get_job: Callable[[str], Job | None],
    ) -> None:
        self._client = client
        self._get_job = get_job

    def renew_lease(
        self,
        lease: JobLease,
        *,
        now: datetime,
        extension_seconds: int,
    ) -> LeaseRenewalResult:
        """Extend ``lease_expires_at`` under CAS (owner + fencing_token + not-yet-expired)."""
        now_utc = _ensure_utc(now) or datetime.now(timezone.utc)
        duration = max(1, int(extension_seconds or 0))
        new_expires_at = now_utc + timedelta(seconds=duration)
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE inventory_jobs
                SET lease_expires_at = ?, last_heartbeat_at = ?, updated_at = ?
                WHERE id = ?
                  AND status IN (?, ?)
                  AND claim_owner_id = ?
                  AND lease_fencing_token = ?
                  AND lease_expires_at >= ?
                """,
                (
                    new_expires_at,
                    now_utc,
                    now_utc,
                    lease.job_id,
                    JobStatus.RUNNING.value,
                    JobStatus.CANCEL_REQUESTED.value,
                    lease.owner_id,
                    lease.fencing_token,
                    now_utc,
                ),
            )
            applied = int(cur.rowcount or 0) == 1

        if applied:
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
            return LeaseRenewalResult(outcome=LeaseRenewalOutcome.RENEWED, lease=renewed)

        job = self._get_job(lease.job_id)
        result = classify_lease_renewal_after_cas_miss(
            job, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now_utc
        )
        logger.warning(
            "event=job_lease_lost job_id=%s owner_id=%s fencing_token=%s outcome=%s reason=%s",
            lease.job_id,
            lease.owner_id,
            lease.fencing_token,
            result.outcome.value,
            result.reason,
        )
        return result

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
        now_utc = _ensure_utc(now) or datetime.now(timezone.utc)
        duration = max(1, int(extension_seconds or 0))
        new_expires_at = now_utc + timedelta(seconds=duration)
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE inventory_jobs
                SET claim_owner_id = ?,
                    lease_fencing_token = lease_fencing_token + 1,
                    lease_acquired_at = ?,
                    lease_expires_at = ?,
                    last_heartbeat_at = ?,
                    updated_at = ?
                OUTPUT inserted.lease_fencing_token
                WHERE id = ?
                  AND status = ?
                  AND lease_expires_at < ?
                """,
                (
                    owner,
                    now_utc,
                    new_expires_at,
                    now_utc,
                    now_utc,
                    job_id,
                    JobStatus.RUNNING.value,
                    now_utc,
                ),
            )
            row = cur.fetchone()
        if row is None:
            job = self._get_job(job_id)
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
            return JobClaimResult(
                outcome=JobClaimOutcome.CONFLICT,
                job=job,
                previous_status=status_value,
                reason="lease_not_expired_or_not_running",
                claim_owner_id=owner,
            )

        raw_token = getattr(row, "lease_fencing_token", None)
        if raw_token is None:
            try:
                raw_token = row[0]
            except Exception:
                raw_token = None
        fencing_token = int(raw_token) if raw_token is not None else 0
        job = self._get_job(job_id)
        lease = JobLease(
            job_id=job_id,
            owner_id=owner,
            fencing_token=fencing_token,
            acquired_at=now_utc,
            expires_at=new_expires_at,
        )
        logger.warning(
            "event=job_lease_reacquired job_id=%s new_owner_id=%s fencing_token=%s expires_at=%s",
            job_id,
            owner,
            fencing_token,
            new_expires_at.isoformat(),
        )
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
        """Merge ``result_json`` only while the caller still holds the lease."""
        now_utc = _ensure_utc(now) or datetime.now(timezone.utc)
        if not patch:
            job = self._get_job(lease.job_id)
            if lease_is_currently_valid(
                job, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now_utc
            ):
                return LeaseWriteResult(outcome=LeaseWriteOutcome.APPLIED), job
            result = classify_lease_write_after_cas_miss(
                job, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now_utc
            )
            return result, job

        with self._client.begin_transaction() as txn:
            cur = txn.connection.cursor()
            try:
                cur.execute(
                    """
                    SELECT result_json, status, claim_owner_id, lease_fencing_token, lease_expires_at
                    FROM inventory_jobs WITH (UPDLOCK, ROWLOCK)
                    WHERE id = ?
                    """,
                    (lease.job_id,),
                )
                row = cur.fetchone()
                if row is None:
                    txn.rollback()
                    return (
                        LeaseWriteResult(outcome=LeaseWriteOutcome.NOT_FOUND, reason="job_not_found"),
                        None,
                    )

                status_value = str(getattr(row, "status", None) or "")
                persisted_owner = normalize_db_str(getattr(row, "claim_owner_id", None))
                persisted_token = int(getattr(row, "lease_fencing_token", 0) or 0)
                expires_at = _ensure_utc(getattr(row, "lease_expires_at", None))

                if status_value in TERMINAL_JOB_STATUSES:
                    txn.rollback()
                    logger.warning(
                        "event=job_stale_write_rejected job_id=%s owner_id=%s fencing_token=%s "
                        "reason=job_terminal",
                        lease.job_id,
                        lease.owner_id,
                        lease.fencing_token,
                    )
                    return (
                        LeaseWriteResult(
                            outcome=LeaseWriteOutcome.JOB_TERMINAL,
                            reason=f"job_terminal:{status_value}",
                        ),
                        self._get_job(lease.job_id),
                    )
                if status_value not in (JobStatus.RUNNING.value, JobStatus.CANCEL_REQUESTED.value):
                    txn.rollback()
                    logger.warning(
                        "event=job_stale_write_rejected job_id=%s owner_id=%s fencing_token=%s "
                        "reason=invalid_state:%s",
                        lease.job_id,
                        lease.owner_id,
                        lease.fencing_token,
                        status_value,
                    )
                    return (
                        LeaseWriteResult(
                            outcome=LeaseWriteOutcome.INVALID_STATE,
                            reason=f"status_not_leasable:{status_value}",
                        ),
                        self._get_job(lease.job_id),
                    )
                if (
                    persisted_owner != (lease.owner_id or "").strip()
                    or persisted_token != lease.fencing_token
                ):
                    txn.rollback()
                    logger.warning(
                        "event=job_stale_write_rejected job_id=%s owner_id=%s fencing_token=%s "
                        "persisted_owner=%s persisted_token=%s reason=owner_or_fencing_token_mismatch",
                        lease.job_id,
                        lease.owner_id,
                        lease.fencing_token,
                        persisted_owner,
                        persisted_token,
                    )
                    return (
                        LeaseWriteResult(
                            outcome=LeaseWriteOutcome.LEASE_LOST,
                            reason="owner_or_fencing_token_mismatch",
                        ),
                        self._get_job(lease.job_id),
                    )
                if expires_at is not None and expires_at < now_utc:
                    txn.rollback()
                    logger.warning(
                        "event=job_stale_write_rejected job_id=%s owner_id=%s fencing_token=%s "
                        "reason=lease_expired",
                        lease.job_id,
                        lease.owner_id,
                        lease.fencing_token,
                    )
                    return (
                        LeaseWriteResult(outcome=LeaseWriteOutcome.LEASE_LOST, reason="lease_expired"),
                        self._get_job(lease.job_id),
                    )

                current = _parse_json(getattr(row, "result_json", None)) or {}
                if not isinstance(current, dict):
                    current = {}
                merged = dict(current)
                merged.update(patch)
                cur.execute(
                    """
                    UPDATE inventory_jobs
                    SET result_json = ?, updated_at = ?
                    WHERE id = ?
                      AND claim_owner_id = ?
                      AND lease_fencing_token = ?
                      AND lease_expires_at >= ?
                      AND status IN (?, ?)
                    """,
                    (
                        json.dumps(merged, ensure_ascii=False),
                        now_utc,
                        lease.job_id,
                        lease.owner_id,
                        lease.fencing_token,
                        now_utc,
                        JobStatus.RUNNING.value,
                        JobStatus.CANCEL_REQUESTED.value,
                    ),
                )
                if int(cur.rowcount or 0) != 1:
                    txn.rollback()
                    job = self._get_job(lease.job_id)
                    result = classify_lease_write_after_cas_miss(
                        job,
                        owner_id=lease.owner_id,
                        fencing_token=lease.fencing_token,
                        now=now_utc,
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
                txn.commit()
            except Exception:
                txn.rollback()
                raise
            finally:
                cur.close()
        return LeaseWriteResult(outcome=LeaseWriteOutcome.APPLIED), self._get_job(lease.job_id)

    def touch_heartbeat_if_leased(
        self,
        lease: JobLease,
        *,
        now: datetime,
        extension_seconds: int,
    ) -> LeaseRenewalResult:
        return self.renew_lease(lease, now=now, extension_seconds=extension_seconds)

    def assert_lease(self, lease: JobLease, *, now: datetime) -> LeaseWriteResult:
        now_utc = _ensure_utc(now) or datetime.now(timezone.utc)
        job = self._get_job(lease.job_id)
        if lease_is_currently_valid(
            job, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now_utc
        ):
            return LeaseWriteResult(outcome=LeaseWriteOutcome.APPLIED)
        return classify_lease_write_after_cas_miss(
            job, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now_utc
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
        now_utc = _ensure_utc(now) or datetime.now(timezone.utc)
        result_str = json.dumps(job.result_json, ensure_ascii=False) if job.result_json else None
        finalization_meta_str = (
            json.dumps(job.finalization_error_metadata, ensure_ascii=False)
            if job.finalization_error_metadata
            else None
        )
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                UPDATE inventory_jobs
                SET status = ?,
                    result_json = ?,
                    error_message = NULL,
                    failure_code = NULL,
                    failure_message = NULL,
                    finalization_error_code = NULL,
                    finalization_error_metadata = ?,
                    updated_at = ?,
                    finished_at = ?,
                    last_heartbeat_at = ?,
                    current_stage = ?,
                    current_substep = ?,
                    prompt_version = ?
                WHERE id = ?
                {LEASE_ACTIVE_PREDICATE_SQL}
                """,
                (
                    JobStatus.SUCCEEDED.value,
                    result_str,
                    finalization_meta_str,
                    now_utc,
                    _ensure_utc(job.finished_at) or now_utc,
                    _ensure_utc(job.last_heartbeat_at) or now_utc,
                    job.current_stage,
                    job.current_substep,
                    job.prompt_version,
                    lease.job_id,
                    *lease_active_bind_params(lease, now_utc=now_utc),
                ),
            )
            applied = int(cur.rowcount or 0) == 1
        if applied:
            return LeaseWriteResult(outcome=LeaseWriteOutcome.APPLIED)
        persisted = self._get_job(lease.job_id)
        result = classify_lease_write_after_cas_miss(
            persisted, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now_utc
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

    def fail_if_leased(
        self,
        lease: JobLease,
        *,
        now: datetime,
        error_message: str,
        failure_code: str = "PROCESSING_FAILED",
    ) -> LeaseWriteResult:
        now_utc = _ensure_utc(now) or datetime.now(timezone.utc)
        msg = error_message[:2048] if len(error_message) > 2048 else error_message
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                UPDATE inventory_jobs
                SET status = ?,
                    updated_at = ?,
                    finished_at = ?,
                    last_heartbeat_at = ?,
                    failure_code = ?,
                    failure_message = ?,
                    error_message = ?
                WHERE id = ?
                {LEASE_ACTIVE_PREDICATE_SQL}
                """,
                (
                    JobStatus.FAILED.value,
                    now_utc,
                    now_utc,
                    now_utc,
                    failure_code,
                    msg,
                    msg,
                    lease.job_id,
                    *lease_active_bind_params(lease, now_utc=now_utc),
                ),
            )
            applied = int(cur.rowcount or 0) == 1
        if applied:
            return LeaseWriteResult(outcome=LeaseWriteOutcome.APPLIED)
        persisted = self._get_job(lease.job_id)
        result = classify_lease_write_after_cas_miss(
            persisted, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now_utc
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

    def update_finalization_if_leased(
        self,
        lease: JobLease,
        *,
        now: datetime,
        mutator,
    ) -> LeaseWriteResult:
        now_utc = _ensure_utc(now) or datetime.now(timezone.utc)
        job = self._get_job(lease.job_id)
        if not lease_allows_finalization_write(
            job, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now_utc
        ):
            result = classify_lease_write_after_cas_miss(
                job, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now_utc
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
        assert job is not None
        mutator(job)
        job.updated_at = now_utc
        finalization_meta_str = (
            json.dumps(job.finalization_error_metadata, ensure_ascii=False)
            if job.finalization_error_metadata
            else None
        )
        result_str = json.dumps(job.result_json, ensure_ascii=False) if job.result_json else None
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE inventory_jobs
                SET status = ?,
                    result_json = ?,
                    error_message = ?,
                    failure_code = ?,
                    failure_message = ?,
                    updated_at = ?,
                    finished_at = ?,
                    last_heartbeat_at = ?,
                    current_stage = ?,
                    current_substep = ?,
                    finalization_status = ?,
                    current_finalization_step = ?,
                    last_completed_finalization_step = ?,
                    finalization_error_code = ?,
                    finalization_error_metadata = ?,
                    finalization_started_at = ?,
                    finalization_completed_at = ?,
                    domain_persisted_at = ?,
                    artifacts_published_at = ?
                WHERE id = ?
                  AND status IN (?, ?, ?)
                  AND claim_owner_id = ?
                  AND lease_fencing_token = ?
                  AND (
                        status = ?
                     OR (lease_expires_at IS NOT NULL AND lease_expires_at >= ?)
                  )
                """,
                (
                    job.status.value,
                    result_str,
                    job.error_message,
                    job.failure_code,
                    job.failure_message,
                    now_utc,
                    _ensure_utc(job.finished_at),
                    _ensure_utc(job.last_heartbeat_at),
                    job.current_stage,
                    job.current_substep,
                    job.finalization_status.value,
                    job.current_finalization_step.value if job.current_finalization_step else None,
                    job.last_completed_finalization_step.value,
                    job.finalization_error_code,
                    finalization_meta_str,
                    _ensure_utc(job.finalization_started_at),
                    _ensure_utc(job.finalization_completed_at),
                    _ensure_utc(job.domain_persisted_at),
                    _ensure_utc(job.artifacts_published_at),
                    lease.job_id,
                    JobStatus.RUNNING.value,
                    JobStatus.CANCEL_REQUESTED.value,
                    JobStatus.SUCCEEDED.value,
                    lease.owner_id,
                    lease.fencing_token,
                    JobStatus.SUCCEEDED.value,
                    now_utc,
                ),
            )
            applied = int(cur.rowcount or 0) == 1
        if applied:
            return LeaseWriteResult(outcome=LeaseWriteOutcome.APPLIED)
        persisted = self._get_job(lease.job_id)
        result = classify_lease_write_after_cas_miss(
            persisted, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now_utc
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

    def acknowledge_cancel_if_leased(
        self,
        lease: JobLease,
        *,
        now: datetime,
        reason: str,
    ) -> LeaseWriteResult:
        now_utc = _ensure_utc(now) or datetime.now(timezone.utc)
        msg = reason[:2048] if len(reason) > 2048 else reason
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE inventory_jobs
                SET status = ?,
                    updated_at = ?,
                    finished_at = ?,
                    last_heartbeat_at = ?,
                    failure_code = ?,
                    failure_message = ?,
                    error_message = ?
                WHERE id = ?
                  AND status IN (?, ?)
                  AND claim_owner_id = ?
                  AND lease_fencing_token = ?
                  AND lease_expires_at >= ?
                """,
                (
                    JobStatus.CANCELED.value,
                    now_utc,
                    now_utc,
                    now_utc,
                    "CANCELED",
                    msg,
                    msg,
                    lease.job_id,
                    JobStatus.RUNNING.value,
                    JobStatus.CANCEL_REQUESTED.value,
                    lease.owner_id,
                    lease.fencing_token,
                    now_utc,
                ),
            )
            applied = int(cur.rowcount or 0) == 1
        if applied:
            return LeaseWriteResult(outcome=LeaseWriteOutcome.APPLIED)
        persisted = self._get_job(lease.job_id)
        result = classify_lease_write_after_cas_miss(
            persisted, owner_id=lease.owner_id, fencing_token=lease.fencing_token, now=now_utc
        )
        logger.warning(
            "event=job_stale_write_rejected job_id=%s operation=acknowledge_cancel owner_id=%s "
            "fencing_token=%s outcome=%s reason=%s",
            lease.job_id,
            lease.owner_id,
            lease.fencing_token,
            result.outcome.value,
            result.reason,
        )
        return result
