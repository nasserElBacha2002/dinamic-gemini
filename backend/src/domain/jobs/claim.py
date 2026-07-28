"""Atomic job claim outcomes (Phase 1 corrections).

``execution_id`` identifies the persisted attempt row.
``claim_owner_id`` identifies the concrete worker process that acquired RUNNING.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.jobs.entities import Job
    from src.domain.jobs.lease import JobLease


class JobClaimOutcome(str, Enum):
    """Result of attempting to acquire STARTING → RUNNING."""

    ACQUIRED = "acquired"
    ALREADY_OWNED = "already_owned"
    CONFLICT = "conflict"
    NOT_FOUND = "not_found"
    TERMINAL = "terminal"
    INVALID_STATUS = "invalid_status"
    TARGET_NOT_FOUND = "target_not_found"
    TARGET_MISMATCH = "target_mismatch"
    TARGET_INVALID_STATUS = "target_invalid_status"


TERMINAL_JOB_STATUSES = frozenset(
    {
        "succeeded",
        "failed",
        "canceled",
        "timed_out",
    }
)


@dataclass(frozen=True)
class JobClaimResult:
    outcome: JobClaimOutcome
    job: Job | None = None
    aisle_transition_applied: bool = False
    reason: str | None = None
    previous_status: str | None = None
    claim_owner_id: str | None = None
    #: Phase 3 — lease acquired/current on ACQUIRED or ALREADY_OWNED outcomes. None otherwise.
    lease: JobLease | None = None

    @property
    def acquired(self) -> bool:
        return self.outcome == JobClaimOutcome.ACQUIRED

    @property
    def may_execute(self) -> bool:
        """Only ACQUIRED or same-owner idempotent ALREADY_OWNED may run the pipeline."""
        return self.outcome in (
            JobClaimOutcome.ACQUIRED,
            JobClaimOutcome.ALREADY_OWNED,
        )


@dataclass(frozen=True)
class StaleReclaimResult:
    won: bool
    job: Job | None = None
    aisle_transition_applied: bool = False
    reason: str | None = None
