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

#: Finalization metadata may still advance after SUCCEEDED under the completing owner/token.
LEASE_FINALIZATION_WRITE_STATUSES = frozenset(
    {JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED, JobStatus.SUCCEEDED}
)


def _status_value(job: Job) -> str:
    return job.status.value if isinstance(job.status, JobStatus) else str(job.status)


def lease_is_initialized(job: Job) -> bool:
    """True when the job row has a usable lease (owner, token >= 1, non-null expiry)."""
    owner = (job.claim_owner_id or "").strip()
    if not owner:
        return False
    if int(job.lease_fencing_token or 0) < 1:
        return False
    if job.lease_expires_at is None:
        return False
    return True


def lease_owner_token_match(
    job: Job | None,
    *,
    owner_id: str,
    fencing_token: int,
) -> bool:
    if job is None:
        return False
    if int(fencing_token) < 1 or not (owner_id or "").strip():
        return False
    if not lease_is_initialized(job):
        return False
    persisted_owner = (job.claim_owner_id or "").strip()
    return persisted_owner == (owner_id or "").strip() and int(job.lease_fencing_token or 0) == int(
        fencing_token
    )


def lease_is_currently_valid(
    job: Job | None,
    *,
    owner_id: str,
    fencing_token: int,
    now: datetime,
) -> bool:
    """True when ``job`` is still actively held by ``owner_id``/``fencing_token`` at ``now``.

    ``lease_expires_at=NULL`` is never treated as infinite — it means uninitialized.
    """
    if job is None or job.status not in LEASE_ACTIVE_STATUSES:
        return False
    if not lease_owner_token_match(job, owner_id=owner_id, fencing_token=fencing_token):
        return False
    expires_at = job.lease_expires_at
    assert expires_at is not None  # guarded by lease_is_initialized
    if expires_at < now:
        return False
    return True


def lease_allows_finalization_write(
    job: Job | None,
    *,
    owner_id: str,
    fencing_token: int,
    now: datetime,
) -> bool:
    """True when finalization metadata may be written under ``owner_id``/``fencing_token``.

    Allows RUNNING / CANCEL_REQUESTED (with unexpired lease) and SUCCEEDED (same owner/token)
    so post-terminalization steps (promote, aisle update, inventory reconcile) stay fenced.
    """
    if job is None or job.status not in LEASE_FINALIZATION_WRITE_STATUSES:
        return False
    if not lease_owner_token_match(job, owner_id=owner_id, fencing_token=fencing_token):
        return False
    if job.status == JobStatus.SUCCEEDED:
        return True
    expires_at = job.lease_expires_at
    assert expires_at is not None
    return expires_at >= now


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

    if not lease_is_initialized(job):
        return LeaseRenewalResult(
            outcome=LeaseRenewalOutcome.LEASE_NOT_INITIALIZED,
            reason="lease_not_initialized",
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
    """Classify why a lease-conditioned write affected 0 rows."""
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

    if not lease_is_initialized(job):
        return LeaseWriteResult(
            outcome=LeaseWriteOutcome.LEASE_NOT_INITIALIZED,
            reason="lease_not_initialized",
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
