"""SQL Server JobProcessingLeaseRepository (Phase 2 corrections).

See :mod:`src.infrastructure.repositories.sql_job_asset_processing_state_repository` module
docstring for the ``SqlServerClient`` cursor-only API note.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

import pyodbc

from src.application.ports.image_processing_repositories import JobProcessingLeaseRepository
from src.database.sqlserver import SqlServerClient
from src.domain.image_processing.job_processing_lease import (
    JobProcessingLease,
    JobProcessingLeaseStatus,
)
from src.infrastructure.repositories.db_row_text import normalize_db_str

logger = logging.getLogger(__name__)

_SELECT_FIELDS = (
    "id, job_id, strategy, execution_scope, status, worker_token, acquired_at, "
    "heartbeat_at, lease_expires_at, released_at, created_at, updated_at, version"
)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _is_lease_scope_unique_violation(exc: pyodbc.IntegrityError) -> bool:
    """True only for ``UQ_job_processing_leases_scope`` (concurrent first-acquire races)."""
    return "uq_job_processing_leases_scope" in str(exc).lower()


def _row_to_lease(row: object) -> JobProcessingLease:
    status_raw = normalize_db_str(getattr(row, "status", None)) or "AVAILABLE"
    try:
        status = JobProcessingLeaseStatus(status_raw)
    except ValueError:
        logger.error("invalid_persisted_job_processing_lease_status value=%s", status_raw)
        raise
    return JobProcessingLease(
        id=str(getattr(row, "id")),
        job_id=str(getattr(row, "job_id")),
        strategy=str(getattr(row, "strategy")),
        execution_scope=str(getattr(row, "execution_scope")),
        status=status,
        worker_token=normalize_db_str(getattr(row, "worker_token", None)),
        acquired_at=_ensure_utc(getattr(row, "acquired_at", None)),
        heartbeat_at=_ensure_utc(getattr(row, "heartbeat_at", None)),
        lease_expires_at=_ensure_utc(getattr(row, "lease_expires_at", None)),
        released_at=_ensure_utc(getattr(row, "released_at", None)),
        created_at=_ensure_utc(getattr(row, "created_at")) or datetime.now(timezone.utc),
        updated_at=_ensure_utc(getattr(row, "updated_at")) or datetime.now(timezone.utc),
        version=int(getattr(row, "version", 1) or 1),
    )


class SqlJobProcessingLeaseRepository(JobProcessingLeaseRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def try_acquire_lease(
        self,
        *,
        job_id: str,
        strategy: str,
        execution_scope: str,
        worker_token: str,
        now: datetime,
        lease_duration_seconds: int,
    ) -> JobProcessingLease | None:
        expires = now + timedelta(seconds=lease_duration_seconds)
        select_fields = ", ".join(f"inserted.{f.strip()}" for f in _SELECT_FIELDS.split(","))
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                UPDATE job_processing_leases
                SET status = 'ACQUIRED', worker_token = ?, acquired_at = ?, heartbeat_at = ?,
                    lease_expires_at = ?, released_at = NULL, updated_at = ?,
                    version = version + 1
                OUTPUT {select_fields}
                WHERE job_id = ? AND strategy = ? AND execution_scope = ?
                  AND (status <> 'ACQUIRED' OR lease_expires_at < ?)
                """,  # nosec B608
                (
                    worker_token,
                    now,
                    now,
                    expires,
                    now,
                    job_id,
                    strategy,
                    execution_scope,
                    now,
                ),
            )
            row = cur.fetchone()
        if row is not None:
            return _row_to_lease(row)

        # No existing row matched: either it does not exist yet, or it is ACQUIRED and live
        # (held by another worker). Attempt a fresh insert; the unique index distinguishes
        # the two cases without a second round-trip race window.
        lease_id = str(uuid.uuid4())
        try:
            with self._client.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO job_processing_leases (
                        id, job_id, strategy, execution_scope, status, worker_token,
                        acquired_at, heartbeat_at, lease_expires_at, released_at,
                        created_at, updated_at, version
                    ) VALUES (?, ?, ?, ?, 'ACQUIRED', ?, ?, ?, ?, NULL, ?, ?, 1)
                    """,
                    (
                        lease_id,
                        job_id,
                        strategy,
                        execution_scope,
                        worker_token,
                        now,
                        now,
                        expires,
                        now,
                        now,
                    ),
                )
        except pyodbc.IntegrityError as exc:
            if _is_lease_scope_unique_violation(exc):
                logger.info(
                    "job_processing_lease.acquire_lost_race job_id=%s strategy=%s scope=%s",
                    job_id,
                    strategy,
                    execution_scope,
                )
                return None
            raise
        return self.get_by_job_strategy_scope(job_id, strategy, execution_scope)

    def heartbeat(
        self,
        lease_id: str,
        *,
        worker_token: str,
        now: datetime,
        lease_duration_seconds: int,
    ) -> JobProcessingLease | None:
        expires = now + timedelta(seconds=lease_duration_seconds)
        select_fields = ", ".join(f"inserted.{f.strip()}" for f in _SELECT_FIELDS.split(","))
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                UPDATE job_processing_leases
                SET heartbeat_at = ?, lease_expires_at = ?, updated_at = ?,
                    version = version + 1
                OUTPUT {select_fields}
                WHERE id = ? AND worker_token = ? AND status = 'ACQUIRED'
                """,  # nosec B608
                (now, expires, now, lease_id, worker_token),
            )
            row = cur.fetchone()
        return _row_to_lease(row) if row is not None else None

    def release(self, lease_id: str, *, worker_token: str, now: datetime) -> None:
        self._finish(lease_id, worker_token=worker_token, now=now, status="AVAILABLE")

    def complete(self, lease_id: str, *, worker_token: str, now: datetime) -> None:
        self._finish(lease_id, worker_token=worker_token, now=now, status="COMPLETED")

    def fail(
        self,
        lease_id: str,
        *,
        worker_token: str,
        now: datetime,
        error_message: str | None = None,
    ) -> None:
        _ = error_message  # not persisted on the lease row (kept on the batch attempt)
        self._finish(lease_id, worker_token=worker_token, now=now, status="FAILED")

    def _finish(
        self, lease_id: str, *, worker_token: str, now: datetime, status: str
    ) -> None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE job_processing_leases
                SET status = ?, released_at = ?, updated_at = ?, version = version + 1
                WHERE id = ? AND worker_token = ?
                """,
                (status, now, now, lease_id, worker_token),
            )

    def get_by_job_strategy_scope(
        self, job_id: str, strategy: str, execution_scope: str
    ) -> JobProcessingLease | None:
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_SELECT_FIELDS} FROM job_processing_leases
                WHERE job_id = ? AND strategy = ? AND execution_scope = ?
                """,  # nosec B608
                (job_id, strategy, execution_scope),
            )
            row = cur.fetchone()
        return _row_to_lease(row) if row is not None else None

    def recover_expired(
        self, *, now: datetime, limit: int = 100
    ) -> Sequence[JobProcessingLease]:
        select_fields = ", ".join(f"inserted.{f.strip()}" for f in _SELECT_FIELDS.split(","))
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                ;WITH expired AS (
                    SELECT TOP (?) id
                    FROM job_processing_leases WITH (UPDLOCK, READPAST, ROWLOCK)
                    WHERE status = 'ACQUIRED' AND lease_expires_at < ?
                    ORDER BY lease_expires_at ASC
                )
                UPDATE job_processing_leases
                SET status = 'AVAILABLE', released_at = ?, updated_at = ?, version = version + 1
                OUTPUT {select_fields}
                WHERE id IN (SELECT id FROM expired)
                """,  # nosec B608
                (limit, now, now, now),
            )
            rows = cur.fetchall()
        return [_row_to_lease(r) for r in rows]
