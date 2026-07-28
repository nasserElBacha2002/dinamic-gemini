"""Job lease fencing (Phase 3) — ownership + monotonic fencing token + expiry."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class LeaseWriteOutcome(str, Enum):
    """Result of a lease-conditioned job write (not an infrastructure error)."""

    APPLIED = "applied"
    LEASE_LOST = "lease_lost"
    JOB_TERMINAL = "job_terminal"
    NOT_FOUND = "not_found"
    INVALID_STATE = "invalid_state"


class LeaseRenewalOutcome(str, Enum):
    RENEWED = "renewed"
    LEASE_LOST = "lease_lost"
    JOB_TERMINAL = "job_terminal"
    NOT_FOUND = "not_found"
    INVALID_STATE = "invalid_state"
    EXPIRED = "expired"


@dataclass(frozen=True)
class JobLease:
    """Active exclusive lease for a running inventory job (Phase 3).

    ``owner_id`` is the worker token (same value as ``Job.claim_owner_id``).
    ``fencing_token`` is assigned by persistence on acquire/reacquire — never invented by callers.
    """

    job_id: str
    owner_id: str
    fencing_token: int
    acquired_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class LeaseRenewalResult:
    outcome: LeaseRenewalOutcome
    lease: JobLease | None = None
    reason: str | None = None

    @property
    def renewed(self) -> bool:
        return self.outcome == LeaseRenewalOutcome.RENEWED


@dataclass(frozen=True)
class LeaseWriteResult:
    outcome: LeaseWriteOutcome
    reason: str | None = None

    @property
    def applied(self) -> bool:
        return self.outcome == LeaseWriteOutcome.APPLIED


class JobLeaseLostError(Exception):
    """Cooperative halt: this worker no longer owns the lease (do not mark job FAILED)."""

    def __init__(
        self,
        message: str = "Job lease lost",
        *,
        job_id: str | None = None,
        owner_id: str | None = None,
        fencing_token: int | None = None,
        reason: str | None = None,
    ) -> None:
        super().__init__(message)
        self.job_id = job_id
        self.owner_id = owner_id
        self.fencing_token = fencing_token
        self.reason = reason
