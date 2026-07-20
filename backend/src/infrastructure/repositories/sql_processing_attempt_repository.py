"""SQL Server ProcessingAttemptRepository (Phase 2 corrections).

See :mod:`src.infrastructure.repositories.sql_job_asset_processing_state_repository` module
docstring for the ``SqlServerClient`` cursor-only API note.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

import pyodbc

from src.application.ports.image_processing_repositories import ProcessingAttemptRepository
from src.database.sqlserver import SqlServerClient
from src.domain.image_processing.processing_attempt import (
    ProcessingAttempt,
    ProcessingAttemptStatus,
)
from src.infrastructure.repositories.db_row_text import normalize_db_str

logger = logging.getLogger(__name__)

_MAX_CREATE_NEXT_ATTEMPT_RETRIES = 3

_SELECT_FIELDS = (
    "id, job_id, asset_id, strategy, provider, model, status, attempt_number, "
    "started_at, finished_at, duration_ms, error_code, error_message, "
    "raw_result_reference, normalized_result_json, validation_result_json, "
    "execution_scope, logical_asset_attempt, configuration_snapshot_version, "
    "parent_batch_attempt_id, batch_execution_id, worker_token, created_at, updated_at, "
    "extra_json"
)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _is_attempt_number_unique_violation(exc: pyodbc.IntegrityError) -> bool:
    """True only for ``UQ_processing_attempts_job_asset_strategy_n`` (concurrent create races)."""
    return "uq_processing_attempts_job_asset_strategy_n" in str(exc).lower()


def _loads(raw: object) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    text = str(raw).strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _row_to_attempt(row: object) -> ProcessingAttempt:
    status_raw = normalize_db_str(getattr(row, "status", None)) or "STARTED"
    try:
        status = ProcessingAttemptStatus(status_raw)
    except ValueError:
        logger.error(
            "invalid_persisted_processing_attempt_status value=%s id=%s",
            status_raw,
            getattr(row, "id", None),
        )
        raise
    logical = getattr(row, "logical_asset_attempt", True)
    return ProcessingAttempt(
        id=str(getattr(row, "id")),
        job_id=str(getattr(row, "job_id")),
        asset_id=str(getattr(row, "asset_id")),
        strategy=str(getattr(row, "strategy")),
        attempt_number=int(getattr(row, "attempt_number") or 1),
        status=status,
        created_at=_ensure_utc(getattr(row, "created_at")) or datetime.now(timezone.utc),
        provider=normalize_db_str(getattr(row, "provider", None)),
        model=normalize_db_str(getattr(row, "model", None)),
        started_at=_ensure_utc(getattr(row, "started_at", None)),
        finished_at=_ensure_utc(getattr(row, "finished_at", None)),
        duration_ms=getattr(row, "duration_ms", None),
        error_code=normalize_db_str(getattr(row, "error_code", None)),
        error_message=normalize_db_str(getattr(row, "error_message", None)),
        raw_result_reference=normalize_db_str(getattr(row, "raw_result_reference", None)),
        normalized_result=_loads(getattr(row, "normalized_result_json", None)),
        validation_result=_loads(getattr(row, "validation_result_json", None)),
        execution_scope=normalize_db_str(getattr(row, "execution_scope", None)),
        logical_asset_attempt=bool(logical) if logical is not None else True,
        configuration_snapshot_version=getattr(row, "configuration_snapshot_version", None),
        parent_batch_attempt_id=normalize_db_str(getattr(row, "parent_batch_attempt_id", None)),
        batch_execution_id=normalize_db_str(getattr(row, "batch_execution_id", None)),
        worker_token=normalize_db_str(getattr(row, "worker_token", None)),
        updated_at=_ensure_utc(getattr(row, "updated_at", None)),
        extra=_loads(getattr(row, "extra_json", None)) or {},
    )


class SqlProcessingAttemptRepository(ProcessingAttemptRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def save(self, attempt: ProcessingAttempt) -> None:
        norm = (
            json.dumps(attempt.normalized_result)
            if attempt.normalized_result is not None
            else None
        )
        valid = (
            json.dumps(attempt.validation_result)
            if attempt.validation_result is not None
            else None
        )
        extra = json.dumps(attempt.extra) if attempt.extra else None
        updated_at = attempt.updated_at or attempt.created_at
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE processing_attempts SET
                    status = ?, provider = ?, model = ?, started_at = ?, finished_at = ?,
                    duration_ms = ?, error_code = ?, error_message = ?,
                    raw_result_reference = ?, normalized_result_json = ?, validation_result_json = ?,
                    execution_scope = ?, logical_asset_attempt = ?,
                    configuration_snapshot_version = ?, parent_batch_attempt_id = ?,
                    batch_execution_id = ?, worker_token = ?, updated_at = ?, extra_json = ?
                WHERE id = ?
                """,
                (
                    attempt.status.value,
                    attempt.provider,
                    attempt.model,
                    attempt.started_at,
                    attempt.finished_at,
                    attempt.duration_ms,
                    attempt.error_code,
                    attempt.error_message,
                    attempt.raw_result_reference,
                    norm,
                    valid,
                    attempt.execution_scope,
                    1 if attempt.logical_asset_attempt else 0,
                    attempt.configuration_snapshot_version,
                    attempt.parent_batch_attempt_id,
                    attempt.batch_execution_id,
                    attempt.worker_token,
                    updated_at,
                    extra,
                    attempt.id,
                ),
            )
            if cur.rowcount == 0:
                cur.execute(
                    """
                    INSERT INTO processing_attempts (
                        id, job_id, asset_id, strategy, provider, model, status, attempt_number,
                        started_at, finished_at, duration_ms, error_code, error_message,
                        raw_result_reference, normalized_result_json, validation_result_json,
                        execution_scope, logical_asset_attempt, configuration_snapshot_version,
                        parent_batch_attempt_id, batch_execution_id, worker_token,
                        created_at, updated_at, extra_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        attempt.id,
                        attempt.job_id,
                        attempt.asset_id,
                        attempt.strategy,
                        attempt.provider,
                        attempt.model,
                        attempt.status.value,
                        attempt.attempt_number,
                        attempt.started_at,
                        attempt.finished_at,
                        attempt.duration_ms,
                        attempt.error_code,
                        attempt.error_message,
                        attempt.raw_result_reference,
                        norm,
                        valid,
                        attempt.execution_scope,
                        1 if attempt.logical_asset_attempt else 0,
                        attempt.configuration_snapshot_version,
                        attempt.parent_batch_attempt_id,
                        attempt.batch_execution_id,
                        attempt.worker_token,
                        attempt.created_at,
                        updated_at,
                        extra,
                    ),
                )

    def get_by_id(self, attempt_id: str) -> ProcessingAttempt | None:
        with self._client.cursor() as cur:
            cur.execute(
                f"SELECT {_SELECT_FIELDS} FROM processing_attempts WHERE id = ?",  # nosec B608
                (attempt_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return _row_to_attempt(row)

    def get_by_unique_key(
        self,
        job_id: str,
        asset_id: str,
        strategy: str,
        attempt_number: int,
    ) -> ProcessingAttempt | None:
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_SELECT_FIELDS} FROM processing_attempts
                WHERE job_id = ? AND asset_id = ? AND strategy = ? AND attempt_number = ?
                """,  # nosec B608
                (job_id, asset_id, strategy, attempt_number),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return _row_to_attempt(row)

    def list_by_job_and_asset(
        self, job_id: str, asset_id: str
    ) -> Sequence[ProcessingAttempt]:
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_SELECT_FIELDS} FROM processing_attempts
                WHERE job_id = ? AND asset_id = ?
                ORDER BY attempt_number ASC, created_at ASC
                """,  # nosec B608
                (job_id, asset_id),
            )
            rows = cur.fetchall()
        return [_row_to_attempt(r) for r in rows]

    def list_by_job(self, job_id: str) -> Sequence[ProcessingAttempt]:
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_SELECT_FIELDS} FROM processing_attempts
                WHERE job_id = ?
                ORDER BY asset_id ASC, attempt_number ASC, created_at ASC
                """,  # nosec B608
                (job_id,),
            )
            rows = cur.fetchall()
        return [_row_to_attempt(r) for r in rows]

    def next_attempt_number(self, job_id: str, asset_id: str, strategy: str) -> int:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT MAX(attempt_number) AS max_n
                FROM processing_attempts
                WHERE job_id = ? AND asset_id = ? AND strategy = ?
                """,
                (job_id, asset_id, strategy),
            )
            row = cur.fetchone()
        if row is None:
            return 1
        max_n = getattr(row, "max_n", None)
        return int(max_n or 0) + 1

    def create_next_attempt(
        self,
        *,
        job_id: str,
        asset_id: str,
        strategy: str,
        status: ProcessingAttemptStatus,
        now: datetime,
        provider: str | None = None,
        model: str | None = None,
        execution_scope: str | None = None,
        configuration_snapshot_version: int | None = None,
        parent_batch_attempt_id: str | None = None,
        batch_execution_id: str | None = None,
        worker_token: str | None = None,
        logical_asset_attempt: bool = True,
    ) -> ProcessingAttempt:
        """Serialize read-max + insert via ``UPDLOCK, HOLDLOCK``; retry on unique-index races.

        The ``SELECT`` and ``INSERT`` share one cursor/connection (one transaction, committed
        on context exit), so the row lock taken by ``UPDLOCK, HOLDLOCK`` is held across both
        statements. A concurrent unique-index violation (defensive fallback if two callers
        somehow bypass the lock, e.g. different isolation level) is retried up to
        ``_MAX_CREATE_NEXT_ATTEMPT_RETRIES`` times.
        """
        last_exc: pyodbc.IntegrityError | None = None
        for _ in range(_MAX_CREATE_NEXT_ATTEMPT_RETRIES):
            attempt_id = str(uuid.uuid4())
            try:
                with self._client.cursor() as cur:
                    cur.execute(
                        """
                        SELECT MAX(attempt_number) AS max_n
                        FROM processing_attempts WITH (UPDLOCK, HOLDLOCK)
                        WHERE job_id = ? AND asset_id = ? AND strategy = ?
                        """,
                        (job_id, asset_id, strategy),
                    )
                    row = cur.fetchone()
                    max_n = getattr(row, "max_n", None) if row is not None else None
                    number = int(max_n or 0) + 1
                    cur.execute(
                        """
                        INSERT INTO processing_attempts (
                            id, job_id, asset_id, strategy, provider, model, status,
                            attempt_number, started_at, execution_scope, logical_asset_attempt,
                            configuration_snapshot_version, parent_batch_attempt_id,
                            batch_execution_id, worker_token, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            attempt_id,
                            job_id,
                            asset_id,
                            strategy,
                            provider,
                            model,
                            status.value,
                            number,
                            now,
                            execution_scope,
                            1 if logical_asset_attempt else 0,
                            configuration_snapshot_version,
                            parent_batch_attempt_id,
                            batch_execution_id,
                            worker_token,
                            now,
                            now,
                        ),
                    )
            except pyodbc.IntegrityError as exc:
                if _is_attempt_number_unique_violation(exc):
                    last_exc = exc
                    logger.warning(
                        "processing_attempts.create_next_attempt_retry job_id=%s asset_id=%s "
                        "strategy=%s",
                        job_id,
                        asset_id,
                        strategy,
                    )
                    continue
                raise
            else:
                return ProcessingAttempt(
                    id=attempt_id,
                    job_id=job_id,
                    asset_id=asset_id,
                    strategy=strategy,
                    attempt_number=number,
                    status=status,
                    created_at=now,
                    provider=provider,
                    model=model,
                    started_at=now,
                    execution_scope=execution_scope,
                    logical_asset_attempt=logical_asset_attempt,
                    configuration_snapshot_version=configuration_snapshot_version,
                    parent_batch_attempt_id=parent_batch_attempt_id,
                    batch_execution_id=batch_execution_id,
                    worker_token=worker_token,
                    updated_at=now,
                )
        raise RuntimeError(
            f"create_next_attempt exhausted retries job_id={job_id} asset_id={asset_id} "
            f"strategy={strategy}"
        ) from last_exc

    def list_started_by_job(self, job_id: str) -> Sequence[ProcessingAttempt]:
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_SELECT_FIELDS} FROM processing_attempts
                WHERE job_id = ? AND status = 'STARTED'
                """,  # nosec B608
                (job_id,),
            )
            rows = cur.fetchall()
        return [_row_to_attempt(r) for r in rows]
