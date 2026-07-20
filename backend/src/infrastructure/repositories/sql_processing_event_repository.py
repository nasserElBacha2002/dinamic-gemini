"""SQL Server ProcessingEventRepository (Phase 7)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import timezone

from src.application.ports.processing_event_repository import ProcessingEventRepository
from src.database.sqlserver import SqlServerClient
from src.domain.image_processing.processing_event import ProcessingEvent


def _to_utc(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _row_to_event(row: object) -> ProcessingEvent:
    meta_raw = getattr(row, "metadata_json", None)
    metadata = {}
    if meta_raw:
        if isinstance(meta_raw, dict):
            metadata = meta_raw
        else:
            metadata = json.loads(str(meta_raw))
    created = getattr(row, "created_at")
    return ProcessingEvent(
        id=str(getattr(row, "id")),
        job_id=str(getattr(row, "job_id")),
        asset_id=(str(getattr(row, "asset_id")) if getattr(row, "asset_id", None) else None),
        attempt_id=(
            str(getattr(row, "attempt_id")) if getattr(row, "attempt_id", None) else None
        ),
        event_type=str(getattr(row, "event_type")),
        severity=str(getattr(row, "severity") or "INFO"),
        strategy=(str(getattr(row, "strategy")) if getattr(row, "strategy", None) else None),
        error_code=(
            str(getattr(row, "error_code")) if getattr(row, "error_code", None) else None
        ),
        message=(str(getattr(row, "message")) if getattr(row, "message", None) else None),
        duration_ms=(
            int(getattr(row, "duration_ms"))
            if getattr(row, "duration_ms", None) is not None
            else None
        ),
        correlation_id=(
            str(getattr(row, "correlation_id"))
            if getattr(row, "correlation_id", None)
            else None
        ),
        metadata=metadata if isinstance(metadata, dict) else {},
        created_at=_to_utc(created),
    )


class SqlProcessingEventRepository(ProcessingEventRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def append(self, event: ProcessingEvent) -> None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                INSERT INTO processing_events (
                    id, job_id, asset_id, attempt_id, event_type, severity, strategy,
                    error_code, message, duration_ms, correlation_id, metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.job_id,
                    event.asset_id,
                    event.attempt_id,
                    event.event_type,
                    event.severity,
                    event.strategy,
                    event.error_code,
                    (event.message or "")[:2000] if event.message else None,
                    event.duration_ms,
                    event.correlation_id,
                    json.dumps(event.metadata or {}, ensure_ascii=False),
                    _to_utc(event.created_at),
                ),
            )

    def list_by_job_asset(
        self,
        job_id: str,
        asset_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[ProcessingEvent]:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, job_id, asset_id, attempt_id, event_type, severity, strategy,
                       error_code, message, duration_ms, correlation_id, metadata_json, created_at
                FROM processing_events
                WHERE job_id = ? AND asset_id = ?
                ORDER BY created_at ASC, id ASC
                OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
                """,
                (job_id, asset_id, int(offset), int(limit)),
            )
            rows = cur.fetchall()
        return [_row_to_event(r) for r in rows]

    def count_by_job_asset(self, job_id: str, asset_id: str) -> int:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(1) AS cnt
                FROM processing_events
                WHERE job_id = ? AND asset_id = ?
                """,
                (job_id, asset_id),
            )
            row = cur.fetchone()
        return int(getattr(row, "cnt", 0) or 0)

    def list_by_job(
        self,
        job_id: str,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> Sequence[ProcessingEvent]:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, job_id, asset_id, attempt_id, event_type, severity, strategy,
                       error_code, message, duration_ms, correlation_id, metadata_json, created_at
                FROM processing_events
                WHERE job_id = ?
                ORDER BY created_at ASC, id ASC
                OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
                """,
                (job_id, int(offset), int(limit)),
            )
            rows = cur.fetchall()
        return [_row_to_event(r) for r in rows]


__all__ = ["SqlProcessingEventRepository"]
