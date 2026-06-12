"""Finalization recovery audit and lease persistence — Phase 3.4."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from src.domain.jobs.finalization_recovery import RecoveryAttemptRecord, RecoveryOperation


class RecoveryLeaseConflictError(Exception):
    """Another active recovery lease exists for the job."""


class FinalizationRecoveryStore(Protocol):
    def get_active_lease(self, job_id: str, *, now: datetime) -> RecoveryAttemptRecord | None:
        """Return a non-expired RUNNING attempt for the job, if any."""

    def begin_attempt(
        self,
        *,
        recovery_id: str,
        job_id: str,
        operation: RecoveryOperation,
        requested_by: str,
        source: str,
        initial_assessment_outcome: str,
        initial_blocking_reason: str | None,
        lease_expires_at: datetime,
        now: datetime,
    ) -> RecoveryAttemptRecord:
        """Create a RUNNING attempt or raise RecoveryLeaseConflictError."""

    def finish_attempt(
        self,
        *,
        attempt_id: str,
        status: str,
        final_assessment_outcome: str | None,
        final_blocking_reason: str | None,
        error_code: str | None,
        sanitized_error: str | None,
        now: datetime,
    ) -> RecoveryAttemptRecord | None:
        """Mark attempt finished."""

    def get_attempt(self, attempt_id: str) -> RecoveryAttemptRecord | None:
        """Fetch attempt by id."""

    def list_attempts(self, job_id: str) -> list[RecoveryAttemptRecord]:
        """List attempts for a job ordered by started_at desc."""
