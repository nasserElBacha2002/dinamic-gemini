"""In-memory finalization recovery store — Phase 3.4."""

from __future__ import annotations

import copy
import uuid
from datetime import datetime

from src.application.ports.finalization_recovery_store import RecoveryLeaseConflictError
from src.domain.jobs.finalization_recovery import RecoveryAttemptRecord, RecoveryAttemptStatus


class MemoryFinalizationRecoveryStore:
    def __init__(self) -> None:
        self._attempts: dict[str, RecoveryAttemptRecord] = {}

    def get_active_lease(self, job_id: str, *, now: datetime) -> RecoveryAttemptRecord | None:
        for rec in self._attempts.values():
            if rec.job_id != job_id:
                continue
            if rec.status != RecoveryAttemptStatus.RUNNING:
                continue
            if rec.lease_expires_at is not None and rec.lease_expires_at <= now:
                continue
            return copy.deepcopy(rec)
        return None

    def begin_attempt(
        self,
        *,
        recovery_id: str,
        job_id: str,
        operation,
        requested_by: str,
        source: str,
        initial_assessment_outcome: str,
        initial_blocking_reason: str | None,
        lease_expires_at: datetime,
        now: datetime,
    ) -> RecoveryAttemptRecord:
        active = self.get_active_lease(job_id, now=now)
        if active is not None:
            raise RecoveryLeaseConflictError(
                f"Active recovery lease job_id={job_id} recovery_id={active.recovery_id}"
            )
        attempt_id = str(uuid.uuid4())
        rec = RecoveryAttemptRecord(
            id=attempt_id,
            recovery_id=recovery_id,
            job_id=job_id,
            operation=operation,
            status=RecoveryAttemptStatus.RUNNING,
            started_at=now,
            requested_by=requested_by,
            source=source,
            initial_assessment_outcome=initial_assessment_outcome,
            initial_blocking_reason=initial_blocking_reason,
            lease_expires_at=lease_expires_at,
            created_at=now,
        )
        self._attempts[attempt_id] = copy.deepcopy(rec)
        return copy.deepcopy(rec)

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
        rec = self._attempts.get(attempt_id)
        if rec is None:
            return None
        rec.status = RecoveryAttemptStatus(status)
        rec.finished_at = now
        rec.final_assessment_outcome = final_assessment_outcome
        rec.final_blocking_reason = final_blocking_reason
        rec.error_code = error_code
        rec.sanitized_error = sanitized_error
        self._attempts[attempt_id] = copy.deepcopy(rec)
        return copy.deepcopy(rec)

    def get_attempt(self, attempt_id: str) -> RecoveryAttemptRecord | None:
        rec = self._attempts.get(attempt_id)
        return copy.deepcopy(rec) if rec is not None else None

    def list_attempts(self, job_id: str) -> list[RecoveryAttemptRecord]:
        rows = [copy.deepcopy(r) for r in self._attempts.values() if r.job_id == job_id]
        rows.sort(key=lambda r: r.started_at, reverse=True)
        return rows
