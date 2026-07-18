"""SQL Server JobAssetProcessingStateRepository (Phase 2 corrections).

``SqlServerClient`` exposes only ``cursor()`` (pyodbc cursor context manager) — there is no
``query()``/``execute()`` convenience wrapper. All access here goes through
``with self._client.cursor() as cur: cur.execute(sql, params)`` and ``cur.fetchone()`` /
``cur.fetchall()`` (see other ``sql_*_repository.py`` modules and
:mod:`src.infrastructure.repositories.sql_job_repository` for the established pattern).

Atomic acquire uses ``UPDATE ... OUTPUT inserted.*`` so the returned row always reflects the
caller's own successful update (never a concurrent winner's row) — see
``claim_next_queued_job`` in ``sql_job_repository.py`` for the same technique.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime, timezone

from src.application.errors import AssetProcessingStateConcurrencyError
from src.application.ports.image_processing_repositories import (
    AssetProgressCounts,
    JobAssetProcessingStateRepository,
)
from src.database.sqlserver import SqlServerClient
from src.domain.image_processing.job_asset_processing_state import (
    JobAssetProcessingState,
    JobAssetProcessingStatus,
)
from src.infrastructure.repositories.db_row_text import normalize_db_str

logger = logging.getLogger(__name__)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


_SELECT_FIELDS = (
    "id, job_id, asset_id, status, active_result_id, attempt_count, "
    "last_strategy, started_at, finished_at, duration_ms, "
    "error_code, error_message, created_at, updated_at, version, execution_scope, "
    "worker_token, lease_expires_at"
)


def _row_to_state(row: object) -> JobAssetProcessingState:
    status_raw = normalize_db_str(getattr(row, "status", None)) or "PENDING"
    try:
        status = JobAssetProcessingStatus(status_raw)
    except ValueError:
        logger.error(
            "invalid_persisted_job_asset_status value=%s job_id=%s asset_id=%s",
            status_raw,
            getattr(row, "job_id", None),
            getattr(row, "asset_id", None),
        )
        raise
    return JobAssetProcessingState(
        id=str(getattr(row, "id")),
        job_id=str(getattr(row, "job_id")),
        asset_id=str(getattr(row, "asset_id")),
        status=status,
        active_result_id=normalize_db_str(getattr(row, "active_result_id", None)),
        attempt_count=int(getattr(row, "attempt_count", 0) or 0),
        last_strategy=normalize_db_str(getattr(row, "last_strategy", None)),
        started_at=_ensure_utc(getattr(row, "started_at", None)),
        finished_at=_ensure_utc(getattr(row, "finished_at", None)),
        duration_ms=getattr(row, "duration_ms", None),
        error_code=normalize_db_str(getattr(row, "error_code", None)),
        error_message=normalize_db_str(getattr(row, "error_message", None)),
        created_at=_ensure_utc(getattr(row, "created_at")) or datetime.now(timezone.utc),
        updated_at=_ensure_utc(getattr(row, "updated_at")) or datetime.now(timezone.utc),
        version=int(getattr(row, "version", 1) or 1),
        execution_scope=normalize_db_str(getattr(row, "execution_scope", None)),
        worker_token=normalize_db_str(getattr(row, "worker_token", None)),
        lease_expires_at=_ensure_utc(getattr(row, "lease_expires_at", None)),
    )


class SqlJobAssetProcessingStateRepository(JobAssetProcessingStateRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def save(self, state: JobAssetProcessingState) -> None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE job_asset_processing_states SET
                    status = ?, active_result_id = ?, attempt_count = ?, last_strategy = ?,
                    started_at = ?, finished_at = ?, duration_ms = ?, error_code = ?,
                    error_message = ?, updated_at = ?, version = ?, execution_scope = ?,
                    worker_token = ?, lease_expires_at = ?
                WHERE job_id = ? AND asset_id = ?
                """,
                (
                    state.status.value,
                    state.active_result_id,
                    state.attempt_count,
                    state.last_strategy,
                    state.started_at,
                    state.finished_at,
                    state.duration_ms,
                    state.error_code,
                    state.error_message,
                    state.updated_at,
                    state.version,
                    state.execution_scope,
                    state.worker_token,
                    state.lease_expires_at,
                    state.job_id,
                    state.asset_id,
                ),
            )
            if cur.rowcount == 0:
                cur.execute(
                    """
                    INSERT INTO job_asset_processing_states (
                        id, job_id, asset_id, status, active_result_id, attempt_count,
                        last_strategy, started_at, finished_at, duration_ms,
                        error_code, error_message, created_at, updated_at, version,
                        execution_scope, worker_token, lease_expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        state.id,
                        state.job_id,
                        state.asset_id,
                        state.status.value,
                        state.active_result_id,
                        state.attempt_count,
                        state.last_strategy,
                        state.started_at,
                        state.finished_at,
                        state.duration_ms,
                        state.error_code,
                        state.error_message,
                        state.created_at,
                        state.updated_at,
                        state.version,
                        state.execution_scope,
                        state.worker_token,
                        state.lease_expires_at,
                    ),
                )

    def save_with_ownership(
        self,
        state: JobAssetProcessingState,
        *,
        expected_version: int,
        worker_token: str | None,
    ) -> None:
        params: list[object] = [
            state.status.value,
            state.active_result_id,
            state.attempt_count,
            state.last_strategy,
            state.started_at,
            state.finished_at,
            state.duration_ms,
            state.error_code,
            state.error_message,
            state.updated_at,
            state.version,
            state.execution_scope,
            state.worker_token,
            state.lease_expires_at,
            state.job_id,
            state.asset_id,
            expected_version,
        ]
        worker_clause = ""
        if worker_token is not None:
            worker_clause = " AND worker_token = ?"
            params.append(worker_token)
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                UPDATE job_asset_processing_states SET
                    status = ?, active_result_id = ?, attempt_count = ?, last_strategy = ?,
                    started_at = ?, finished_at = ?, duration_ms = ?, error_code = ?,
                    error_message = ?, updated_at = ?, version = ?, execution_scope = ?,
                    worker_token = ?, lease_expires_at = ?
                WHERE job_id = ? AND asset_id = ? AND version = ?{worker_clause}
                """,  # nosec B608
                tuple(params),
            )
            if cur.rowcount == 0:
                raise AssetProcessingStateConcurrencyError(
                    f"job_asset_processing_states ownership conflict "
                    f"job_id={state.job_id} asset_id={state.asset_id} "
                    f"expected_version={expected_version} worker_token={worker_token}"
                )

    def get_by_job_and_asset(
        self, job_id: str, asset_id: str
    ) -> JobAssetProcessingState | None:
        with self._client.cursor() as cur:
            cur.execute(
                f"SELECT {_SELECT_FIELDS} FROM job_asset_processing_states "  # nosec B608
                "WHERE job_id = ? AND asset_id = ?",
                (job_id, asset_id),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return _row_to_state(row)

    def list_by_job(self, job_id: str) -> Sequence[JobAssetProcessingState]:
        with self._client.cursor() as cur:
            cur.execute(
                f"SELECT {_SELECT_FIELDS} FROM job_asset_processing_states "  # nosec B608
                "WHERE job_id = ? ORDER BY created_at ASC",
                (job_id,),
            )
            rows = cur.fetchall()
        return [_row_to_state(r) for r in rows]

    def try_acquire(
        self,
        job_id: str,
        asset_id: str,
        *,
        expected_statuses: Sequence[JobAssetProcessingStatus],
        next_status: JobAssetProcessingStatus,
        strategy: str,
        now: datetime,
        worker_token: str | None = None,
    ) -> JobAssetProcessingState | None:
        if not expected_statuses:
            return None
        placeholders = ", ".join("?" for _ in expected_statuses)
        select_fields = ", ".join(f"inserted.{f.strip()}" for f in _SELECT_FIELDS.split(","))
        params: tuple[object, ...] = (
            next_status.value,
            strategy,
            now,
            now,
            worker_token,
            job_id,
            asset_id,
            *[s.value for s in expected_statuses],
        )
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                UPDATE job_asset_processing_states
                SET status = ?, last_strategy = ?, started_at = ?, updated_at = ?,
                    version = version + 1, worker_token = ?
                OUTPUT {select_fields}
                WHERE job_id = ? AND asset_id = ? AND status IN ({placeholders})
                """,  # nosec B608
                params,
            )
            row = cur.fetchone()
        if row is None:
            return None
        return _row_to_state(row)

    def aggregate_progress(self, job_id: str) -> AssetProgressCounts:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT status, COUNT(1) AS cnt
                FROM job_asset_processing_states
                WHERE job_id = ?
                GROUP BY status
                """,
                (job_id,),
            )
            rows = cur.fetchall()
        counts = {
            "PENDING": 0,
            "PROCESSING": 0,
            "RESOLVED": 0,
            "UNRECOGNIZED": 0,
            "FAILED_TECHNICAL": 0,
            "PENDING_MANUAL_REVIEW": 0,
            "CANCELLED": 0,
        }
        total = 0
        for row in rows:
            status = normalize_db_str(getattr(row, "status", None)) or ""
            cnt = int(getattr(row, "cnt", 0) or 0)
            total += cnt
            if status in counts:
                counts[status] = cnt
        return AssetProgressCounts(
            total=total,
            pending=counts["PENDING"],
            processing=counts["PROCESSING"],
            resolved=counts["RESOLVED"],
            unrecognized=counts["UNRECOGNIZED"],
            failed=counts["FAILED_TECHNICAL"],
            manual_review=counts["PENDING_MANUAL_REVIEW"],
            cancelled=counts["CANCELLED"],
        )

    def list_abandoned_processing(
        self,
        *,
        older_than: datetime,
        limit: int = 100,
        job_id: str | None = None,
        as_of: datetime | None = None,
    ) -> Sequence[JobAssetProcessingState]:
        lease_cutoff = as_of if as_of is not None else older_than
        with self._client.cursor() as cur:
            if job_id is not None:
                cur.execute(
                    f"""
                    SELECT TOP (?) {_SELECT_FIELDS}
                    FROM job_asset_processing_states
                    WHERE status = 'PROCESSING'
                      AND job_id = ?
                      AND (
                            (lease_expires_at IS NOT NULL AND lease_expires_at < ?)
                         OR (lease_expires_at IS NULL AND updated_at < ?)
                      )
                    ORDER BY updated_at ASC
                    """,  # nosec B608
                    (limit, job_id, lease_cutoff, older_than),
                )
            else:
                cur.execute(
                    f"""
                    SELECT TOP (?) {_SELECT_FIELDS}
                    FROM job_asset_processing_states
                    WHERE status = 'PROCESSING'
                      AND (
                            (lease_expires_at IS NOT NULL AND lease_expires_at < ?)
                         OR (lease_expires_at IS NULL AND updated_at < ?)
                      )
                    ORDER BY updated_at ASC
                    """,  # nosec B608
                    (limit, lease_cutoff, older_than),
                )
            rows = cur.fetchall()
        return [_row_to_state(r) for r in rows]
