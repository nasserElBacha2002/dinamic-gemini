"""SQL Server ProcessingAttemptRepository (Phase 2)."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from src.application.ports.image_processing_repositories import ProcessingAttemptRepository
from src.database.sqlserver import SqlServerClient
from src.domain.image_processing.processing_attempt import (
    ProcessingAttempt,
    ProcessingAttemptStatus,
)
from src.infrastructure.repositories.db_row_text import normalize_db_str

logger = logging.getLogger(__name__)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


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
    )


class SqlProcessingAttemptRepository(ProcessingAttemptRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def save(self, attempt: ProcessingAttempt) -> None:
        existing = self.get_by_id(attempt.id)
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
        if existing is None:
            self._client.execute(
                """
                INSERT INTO processing_attempts (
                    id, job_id, asset_id, strategy, provider, model, status, attempt_number,
                    started_at, finished_at, duration_ms, error_code, error_message,
                    raw_result_reference, normalized_result_json, validation_result_json,
                    execution_scope, logical_asset_attempt, configuration_snapshot_version,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    attempt.created_at,
                ),
            )
            return
        self._client.execute(
            """
            UPDATE processing_attempts SET
                status = ?, provider = ?, model = ?, started_at = ?, finished_at = ?,
                duration_ms = ?, error_code = ?, error_message = ?,
                raw_result_reference = ?, normalized_result_json = ?, validation_result_json = ?,
                execution_scope = ?, logical_asset_attempt = ?,
                configuration_snapshot_version = ?
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
                attempt.id,
            ),
        )

    def get_by_id(self, attempt_id: str) -> ProcessingAttempt | None:
        rows = self._client.query(
            """
            SELECT id, job_id, asset_id, strategy, provider, model, status, attempt_number,
                   started_at, finished_at, duration_ms, error_code, error_message,
                   raw_result_reference, normalized_result_json, validation_result_json,
                   execution_scope, logical_asset_attempt, configuration_snapshot_version,
                   created_at
            FROM processing_attempts WHERE id = ?
            """,
            (attempt_id,),
        )
        if not rows:
            return None
        return _row_to_attempt(rows[0])

    def get_by_unique_key(
        self,
        job_id: str,
        asset_id: str,
        strategy: str,
        attempt_number: int,
    ) -> ProcessingAttempt | None:
        rows = self._client.query(
            """
            SELECT id, job_id, asset_id, strategy, provider, model, status, attempt_number,
                   started_at, finished_at, duration_ms, error_code, error_message,
                   raw_result_reference, normalized_result_json, validation_result_json,
                   execution_scope, logical_asset_attempt, configuration_snapshot_version,
                   created_at
            FROM processing_attempts
            WHERE job_id = ? AND asset_id = ? AND strategy = ? AND attempt_number = ?
            """,
            (job_id, asset_id, strategy, attempt_number),
        )
        if not rows:
            return None
        return _row_to_attempt(rows[0])

    def list_by_job_and_asset(
        self, job_id: str, asset_id: str
    ) -> Sequence[ProcessingAttempt]:
        rows = self._client.query(
            """
            SELECT id, job_id, asset_id, strategy, provider, model, status, attempt_number,
                   started_at, finished_at, duration_ms, error_code, error_message,
                   raw_result_reference, normalized_result_json, validation_result_json,
                   execution_scope, logical_asset_attempt, configuration_snapshot_version,
                   created_at
            FROM processing_attempts
            WHERE job_id = ? AND asset_id = ?
            ORDER BY attempt_number ASC, created_at ASC
            """,
            (job_id, asset_id),
        )
        return [_row_to_attempt(r) for r in rows]

    def list_by_job(self, job_id: str) -> Sequence[ProcessingAttempt]:
        rows = self._client.query(
            """
            SELECT id, job_id, asset_id, strategy, provider, model, status, attempt_number,
                   started_at, finished_at, duration_ms, error_code, error_message,
                   raw_result_reference, normalized_result_json, validation_result_json,
                   execution_scope, logical_asset_attempt, configuration_snapshot_version,
                   created_at
            FROM processing_attempts
            WHERE job_id = ?
            ORDER BY asset_id ASC, attempt_number ASC, created_at ASC
            """,
            (job_id,),
        )
        return [_row_to_attempt(r) for r in rows]

    def next_attempt_number(self, job_id: str, asset_id: str, strategy: str) -> int:
        rows = self._client.query(
            """
            SELECT MAX(attempt_number) AS max_n
            FROM processing_attempts
            WHERE job_id = ? AND asset_id = ? AND strategy = ?
            """,
            (job_id, asset_id, strategy),
        )
        if not rows:
            return 1
        max_n = getattr(rows[0], "max_n", None)
        return int(max_n or 0) + 1
