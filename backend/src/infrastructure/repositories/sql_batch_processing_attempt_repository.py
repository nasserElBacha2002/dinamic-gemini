"""SQL Server BatchProcessingAttemptRepository (Phase 2 corrections).

See :mod:`src.infrastructure.repositories.sql_job_asset_processing_state_repository` module
docstring for the ``SqlServerClient`` cursor-only API note.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime, timezone

from src.application.ports.image_processing_repositories import (
    BatchProcessingAttemptRepository,
)
from src.database.sqlserver import SqlServerClient
from src.domain.image_processing.batch_processing_attempt import (
    BatchProcessingAttempt,
    BatchProcessingAttemptStatus,
)
from src.infrastructure.repositories.db_row_text import normalize_db_str

logger = logging.getLogger(__name__)

_SELECT_FIELDS = (
    "id, job_id, strategy, execution_scope, provider, model, prompt_key, prompt_version, "
    "status, worker_token, started_at, finished_at, duration_ms, error_code, error_message, "
    "created_at, updated_at"
)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _row_to_attempt(row: object) -> BatchProcessingAttempt:
    status_raw = normalize_db_str(getattr(row, "status", None)) or "STARTED"
    try:
        status = BatchProcessingAttemptStatus(status_raw)
    except ValueError:
        logger.error("invalid_persisted_batch_processing_attempt_status value=%s", status_raw)
        raise
    return BatchProcessingAttempt(
        id=str(getattr(row, "id")),
        job_id=str(getattr(row, "job_id")),
        strategy=str(getattr(row, "strategy")),
        execution_scope=str(getattr(row, "execution_scope")),
        status=status,
        provider=normalize_db_str(getattr(row, "provider", None)),
        model=normalize_db_str(getattr(row, "model", None)),
        prompt_key=normalize_db_str(getattr(row, "prompt_key", None)),
        prompt_version=normalize_db_str(getattr(row, "prompt_version", None)),
        worker_token=normalize_db_str(getattr(row, "worker_token", None)),
        started_at=_ensure_utc(getattr(row, "started_at", None)),
        finished_at=_ensure_utc(getattr(row, "finished_at", None)),
        duration_ms=getattr(row, "duration_ms", None),
        error_code=normalize_db_str(getattr(row, "error_code", None)),
        error_message=normalize_db_str(getattr(row, "error_message", None)),
        created_at=_ensure_utc(getattr(row, "created_at")) or datetime.now(timezone.utc),
        updated_at=_ensure_utc(getattr(row, "updated_at")) or datetime.now(timezone.utc),
    )


class SqlBatchProcessingAttemptRepository(BatchProcessingAttemptRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def create_started(self, attempt: BatchProcessingAttempt) -> BatchProcessingAttempt:
        with self._client.cursor() as cur:
            cur.execute(
                """
                INSERT INTO batch_processing_attempts (
                    id, job_id, strategy, execution_scope, provider, model, prompt_key,
                    prompt_version, status, worker_token, started_at, finished_at, duration_ms,
                    error_code, error_message, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt.id,
                    attempt.job_id,
                    attempt.strategy,
                    attempt.execution_scope,
                    attempt.provider,
                    attempt.model,
                    attempt.prompt_key,
                    attempt.prompt_version,
                    attempt.status.value,
                    attempt.worker_token,
                    attempt.started_at,
                    attempt.finished_at,
                    attempt.duration_ms,
                    attempt.error_code,
                    attempt.error_message,
                    attempt.created_at,
                    attempt.updated_at,
                ),
            )
        return attempt

    def finalize(
        self,
        attempt_id: str,
        *,
        status: BatchProcessingAttemptStatus,
        now: datetime,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> BatchProcessingAttempt | None:
        select_fields = ", ".join(f"inserted.{f.strip()}" for f in _SELECT_FIELDS.split(","))
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                UPDATE batch_processing_attempts
                SET status = ?, finished_at = ?,
                    duration_ms = DATEDIFF(MILLISECOND, COALESCE(started_at, ?), ?),
                    error_code = ?, error_message = ?, updated_at = ?
                OUTPUT {select_fields}
                WHERE id = ?
                """,  # nosec B608
                (status.value, now, now, now, error_code, error_message, now, attempt_id),
            )
            row = cur.fetchone()
        return _row_to_attempt(row) if row is not None else None

    def get_started_by_job(
        self, job_id: str, strategy: str, execution_scope: str
    ) -> Sequence[BatchProcessingAttempt]:
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_SELECT_FIELDS} FROM batch_processing_attempts
                WHERE job_id = ? AND strategy = ? AND execution_scope = ? AND status = 'STARTED'
                """,  # nosec B608
                (job_id, strategy, execution_scope),
            )
            rows = cur.fetchall()
        return [_row_to_attempt(r) for r in rows]
