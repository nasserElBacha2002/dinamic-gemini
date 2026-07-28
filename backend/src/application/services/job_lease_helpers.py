"""Shared helpers for Phase 3 lease-conditioned CAS classification.

Both ``SqlJobRepository`` and ``MemoryJobRepository`` use these helpers so renewal /
write-rejection reasons stay consistent across implementations.
"""

from __future__ import annotations

from datetime import datetime

from src.domain.jobs.claim import TERMINAL_JOB_STATUSES
from src.domain.jobs.entities import Job, JobStatus
from src.domain.jobs.lease import (
    LeaseRenewalOutcome,
    LeaseRenewalResult,
    LeaseWriteOutcome,
    LeaseWriteResult,
)

#: Statuses under which a lease-holding write/renewal may legitimately be attempted.
LEASE_ACTIVE_STATUSES = frozenset({JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED})


def _status_value(job: Job) -> str:
    return job.status.value if isinstance(job.status, JobStatus) else str(job.status)


def lease_is_currently_valid(
    job: Job | None,
    *,
    owner_id: str,
    fencing_token: int,
    now: datetime,
) -> bool:
    """True when ``job`` is still actively held by ``owner_id``/``fencing_token`` at ``now``."""
    if job is None or job.status not in LEASE_ACTIVE_STATUSES:
        return False
    persisted_owner = (job.claim_owner_id or "").strip() or None
    if persisted_owner != (owner_id or "").strip() or int(job.lease_fencing_token or 0) != int(
        fencing_token
    ):
        return False
    expires_at = job.lease_expires_at
    if expires_at is not None and expires_at < now:
        return False
    return True


def classify_lease_renewal_after_cas_miss(
    job: Job | None,
    *,
    owner_id: str,
    fencing_token: int,
    now: datetime,
) -> LeaseRenewalResult:
    """Classify why a ``renew_lease`` CAS UPDATE affected 0 rows."""
    if job is None:
        return LeaseRenewalResult(outcome=LeaseRenewalOutcome.NOT_FOUND, reason="job_not_found")

    status_value = _status_value(job)
    if status_value in TERMINAL_JOB_STATUSES:
        return LeaseRenewalResult(
            outcome=LeaseRenewalOutcome.JOB_TERMINAL,
            reason=f"job_terminal:{status_value}",
        )

    if job.status not in LEASE_ACTIVE_STATUSES:
        return LeaseRenewalResult(
            outcome=LeaseRenewalOutcome.INVALID_STATE,
            reason=f"status_not_leasable:{status_value}",
        )

    persisted_owner = (job.claim_owner_id or "").strip() or None
    if persisted_owner != (owner_id or "").strip() or int(job.lease_fencing_token or 0) != int(
        fencing_token
    ):
        return LeaseRenewalResult(
            outcome=LeaseRenewalOutcome.LEASE_LOST,
            reason="owner_or_fencing_token_mismatch",
        )

    expires_at = job.lease_expires_at
    if expires_at is not None and expires_at < now:
        return LeaseRenewalResult(outcome=LeaseRenewalOutcome.EXPIRED, reason="lease_expired")

    return LeaseRenewalResult(outcome=LeaseRenewalOutcome.INVALID_STATE, reason="cas_miss_unclassified")


def classify_lease_write_after_cas_miss(
    job: Job | None,
    *,
    owner_id: str,
    fencing_token: int,
    now: datetime,
) -> LeaseWriteResult:
    """Classify why a lease-conditioned write (``merge_result_json_if_leased``) affected 0 rows."""
    if job is None:
        return LeaseWriteResult(outcome=LeaseWriteOutcome.NOT_FOUND, reason="job_not_found")

    status_value = _status_value(job)
    if status_value in TERMINAL_JOB_STATUSES:
        return LeaseWriteResult(
            outcome=LeaseWriteOutcome.JOB_TERMINAL,
            reason=f"job_terminal:{status_value}",
        )

    if job.status not in LEASE_ACTIVE_STATUSES:
        return LeaseWriteResult(
            outcome=LeaseWriteOutcome.INVALID_STATE,
            reason=f"status_not_leasable:{status_value}",
        )

    persisted_owner = (job.claim_owner_id or "").strip() or None
    if persisted_owner != (owner_id or "").strip() or int(job.lease_fencing_token or 0) != int(
        fencing_token
    ):
        return LeaseWriteResult(
            outcome=LeaseWriteOutcome.LEASE_LOST,
            reason="owner_or_fencing_token_mismatch",
        )

    expires_at = job.lease_expires_at
    if expires_at is not None and expires_at < now:
        return LeaseWriteResult(outcome=LeaseWriteOutcome.LEASE_LOST, reason="lease_expired")

    return LeaseWriteResult(outcome=LeaseWriteOutcome.INVALID_STATE, reason="cas_miss_unclassified")
