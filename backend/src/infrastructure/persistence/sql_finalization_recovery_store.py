"""SQL Server finalization recovery store — Phase 3.4."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.application.ports.finalization_recovery_store import RecoveryLeaseConflictError
from src.database.sqlserver import SqlServerClient
from src.domain.jobs.finalization_recovery import RecoveryAttemptRecord, RecoveryAttemptStatus
from src.infrastructure.database.sql_transaction import sql_repository_cursor


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


class SqlFinalizationRecoveryStore:
    def __init__(self, client: SqlServerClient, *, connection=None) -> None:
        self._client = client
        self._connection = connection

    def get_active_lease(self, job_id: str, *, now: datetime) -> RecoveryAttemptRecord | None:
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                """
                SELECT TOP 1 id, recovery_id, job_id, operation, status, started_at, finished_at,
                       requested_by, source, initial_assessment_outcome, initial_blocking_reason,
                       final_assessment_outcome, final_blocking_reason, error_code, sanitized_error,
                       lease_expires_at, created_at
                FROM job_finalization_recovery_attempts
                WHERE job_id = ? AND status = ? AND lease_expires_at > ?
                ORDER BY started_at DESC
                """,
                (job_id, RecoveryAttemptStatus.RUNNING.value, now.replace(tzinfo=None)),
            )
            row = cur.fetchone()
            return _row_to_record(row) if row else None

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
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                """
                INSERT INTO job_finalization_recovery_attempts (
                    id, recovery_id, job_id, operation, status, started_at, requested_by, source,
                    initial_assessment_outcome, initial_blocking_reason, lease_expires_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt_id,
                    recovery_id,
                    job_id,
                    operation.value if hasattr(operation, "value") else str(operation),
                    RecoveryAttemptStatus.RUNNING.value,
                    now.replace(tzinfo=None),
                    requested_by,
                    source,
                    initial_assessment_outcome,
                    initial_blocking_reason,
                    lease_expires_at.replace(tzinfo=None),
                    now.replace(tzinfo=None),
                ),
            )
        rec = self.get_attempt(attempt_id)
        assert rec is not None
        return rec

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
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                """
                UPDATE job_finalization_recovery_attempts
                SET status = ?, finished_at = ?, final_assessment_outcome = ?,
                    final_blocking_reason = ?, error_code = ?, sanitized_error = ?
                WHERE id = ?
                """,
                (
                    status,
                    now.replace(tzinfo=None),
                    final_assessment_outcome,
                    final_blocking_reason,
                    error_code,
                    sanitized_error,
                    attempt_id,
                ),
            )
        return self.get_attempt(attempt_id)

    def get_attempt(self, attempt_id: str) -> RecoveryAttemptRecord | None:
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                """
                SELECT id, recovery_id, job_id, operation, status, started_at, finished_at,
                       requested_by, source, initial_assessment_outcome, initial_blocking_reason,
                       final_assessment_outcome, final_blocking_reason, error_code, sanitized_error,
                       lease_expires_at, created_at
                FROM job_finalization_recovery_attempts
                WHERE id = ?
                """,
                (attempt_id,),
            )
            row = cur.fetchone()
            return _row_to_record(row) if row else None

    def list_attempts(self, job_id: str) -> list[RecoveryAttemptRecord]:
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                """
                SELECT id, recovery_id, job_id, operation, status, started_at, finished_at,
                       requested_by, source, initial_assessment_outcome, initial_blocking_reason,
                       final_assessment_outcome, final_blocking_reason, error_code, sanitized_error,
                       lease_expires_at, created_at
                FROM job_finalization_recovery_attempts
                WHERE job_id = ?
                ORDER BY started_at DESC
                """,
                (job_id,),
            )
            return [_row_to_record(row) for row in cur.fetchall()]


def _row_to_record(row) -> RecoveryAttemptRecord:
    from src.domain.jobs.finalization_recovery import RecoveryOperation

    return RecoveryAttemptRecord(
        id=str(row.id),
        recovery_id=str(row.recovery_id),
        job_id=str(row.job_id),
        operation=RecoveryOperation(str(row.operation)),
        status=RecoveryAttemptStatus(str(row.status)),
        started_at=_ensure_utc(row.started_at),
        finished_at=_ensure_utc(getattr(row, "finished_at", None)),
        requested_by=str(row.requested_by),
        source=str(row.source),
        initial_assessment_outcome=str(row.initial_assessment_outcome),
        initial_blocking_reason=getattr(row, "initial_blocking_reason", None),
        final_assessment_outcome=getattr(row, "final_assessment_outcome", None),
        final_blocking_reason=getattr(row, "final_blocking_reason", None),
        error_code=getattr(row, "error_code", None),
        sanitized_error=getattr(row, "sanitized_error", None),
        lease_expires_at=_ensure_utc(getattr(row, "lease_expires_at", None)),
        created_at=_ensure_utc(getattr(row, "created_at", None)),
    )
