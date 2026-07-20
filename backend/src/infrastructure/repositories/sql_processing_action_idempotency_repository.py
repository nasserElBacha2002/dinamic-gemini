"""SQL Server ProcessingActionIdempotencyRepository."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pyodbc

from src.application.errors import IdempotencyKeyReusedError
from src.application.ports.processing_action_idempotency_repository import (
    ProcessingActionIdempotencyRepository,
)
from src.database.sqlserver import SqlServerClient
from src.domain.image_processing.processing_action_idempotency import (
    ProcessingActionIdempotencyRecord,
)


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _row(row: object) -> ProcessingActionIdempotencyRecord:
    raw = getattr(row, "response_json", None)
    response = json.loads(str(raw)) if raw and not isinstance(raw, dict) else (raw or {})
    return ProcessingActionIdempotencyRecord(
        id=str(getattr(row, "id")),
        action_type=str(getattr(row, "action_type")),
        job_id=str(getattr(row, "job_id")),
        asset_id=str(getattr(row, "asset_id")),
        idempotency_key=str(getattr(row, "idempotency_key")),
        request_hash=str(getattr(row, "request_hash")),
        response_json=response if isinstance(response, dict) else {},
        status=str(getattr(row, "status")),
        created_at=_utc(getattr(row, "created_at")) or datetime.now(timezone.utc),
        updated_at=_utc(getattr(row, "updated_at")) or datetime.now(timezone.utc),
        state_version=getattr(row, "state_version", None),
        actor=getattr(row, "actor", None),
    )


class SqlProcessingActionIdempotencyRepository(ProcessingActionIdempotencyRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def get(
        self,
        *,
        action_type: str,
        job_id: str,
        asset_id: str,
        idempotency_key: str,
    ) -> ProcessingActionIdempotencyRecord | None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, action_type, job_id, asset_id, idempotency_key, request_hash,
                       response_json, status, state_version, actor, created_at, updated_at
                FROM processing_action_idempotency
                WHERE action_type = ? AND job_id = ? AND asset_id = ? AND idempotency_key = ?
                """,
                (action_type, job_id, asset_id, idempotency_key),
            )
            row = cur.fetchone()
        return _row(row) if row else None

    def insert(self, record: ProcessingActionIdempotencyRecord) -> None:
        with self._client.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO processing_action_idempotency (
                        id, action_type, job_id, asset_id, idempotency_key, request_hash,
                        response_json, status, state_version, actor, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.id,
                        record.action_type,
                        record.job_id,
                        record.asset_id,
                        record.idempotency_key,
                        record.request_hash,
                        json.dumps(record.response_json or {}, ensure_ascii=False),
                        record.status,
                        record.state_version,
                        record.actor,
                        _utc(record.created_at),
                        _utc(record.updated_at),
                    ),
                )
            except pyodbc.IntegrityError as exc:
                raise IdempotencyKeyReusedError(
                    "IDEMPOTENCY_KEY_REUSED: key already registered"
                ) from exc

    def update_response(self, record: ProcessingActionIdempotencyRecord) -> None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE processing_action_idempotency
                SET response_json = ?, status = ?, state_version = ?, updated_at = ?
                WHERE action_type = ? AND job_id = ? AND asset_id = ? AND idempotency_key = ?
                """,
                (
                    json.dumps(record.response_json or {}, ensure_ascii=False),
                    record.status,
                    record.state_version,
                    _utc(record.updated_at),
                    record.action_type,
                    record.job_id,
                    record.asset_id,
                    record.idempotency_key,
                ),
            )


__all__ = ["SqlProcessingActionIdempotencyRepository"]
