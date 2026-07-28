"""Atomic job claim outcomes (Phase 1 — job integrity).

Ownership token for an execution attempt is ``Job.execution_id`` (already persisted).
Claim must be decided by a compare-and-set ``UPDATE … WHERE status = 'starting'``,
never by a bare read-then-write.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.aisle.entities import Aisle
    from src.domain.jobs.entities import Job


class JobClaimOutcome(str, Enum):
    """Result of attempting to acquire STARTING → RUNNING."""

    ACQUIRED = "acquired"
    ALREADY_OWNED = "already_owned"
    CONFLICT = "conflict"
    NOT_FOUND = "not_found"
    TERMINAL = "terminal"
    INVALID_STATUS = "invalid_status"


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
    aisle: Aisle | None = None
    reason: str | None = None
    previous_status: str | None = None

    @property
    def acquired(self) -> bool:
        return self.outcome == JobClaimOutcome.ACQUIRED

    @property
    def may_execute(self) -> bool:
        """True when the caller may proceed with pipeline execution."""
        return self.outcome in (
            JobClaimOutcome.ACQUIRED,
            JobClaimOutcome.ALREADY_OWNED,
        )
