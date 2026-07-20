"""SQL Server AssetProcessingCommandRepository."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timezone

from src.application.ports.asset_processing_command_repository import (
    AssetProcessingCommandRepository,
)
from src.database.sqlserver import SqlServerClient
from src.domain.image_processing.asset_processing_command import (
    AssetProcessingCommand,
    AssetProcessingCommandStatus,
    AssetProcessingCommandType,
)


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _row_to_cmd(row: object) -> AssetProcessingCommand:
    payload_raw = getattr(row, "payload_json", None)
    payload = {}
    if payload_raw:
        payload = json.loads(str(payload_raw)) if not isinstance(payload_raw, dict) else payload_raw
    return AssetProcessingCommand(
        id=str(getattr(row, "id")),
        job_id=str(getattr(row, "job_id")),
        asset_id=str(getattr(row, "asset_id")),
        command_type=AssetProcessingCommandType(str(getattr(row, "command_type"))),
        status=AssetProcessingCommandStatus(str(getattr(row, "status"))),
        created_at=_utc(getattr(row, "created_at")) or datetime.now(timezone.utc),
        requested_strategy=getattr(row, "requested_strategy", None),
        idempotency_key=getattr(row, "idempotency_key", None),
        expected_state_version=getattr(row, "expected_state_version", None),
        actor=getattr(row, "actor", None),
        reason=getattr(row, "reason", None),
        payload=payload if isinstance(payload, dict) else {},
        worker_token=getattr(row, "worker_token", None),
        claimed_at=_utc(getattr(row, "claimed_at", None)),
        completed_at=_utc(getattr(row, "completed_at", None)),
        error_code=getattr(row, "error_code", None),
        error_message=getattr(row, "error_message", None),
    )


class SqlAssetProcessingCommandRepository(AssetProcessingCommandRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def save(self, command: AssetProcessingCommand) -> None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                MERGE asset_processing_commands AS t
                USING (SELECT ? AS id) AS s ON t.id = s.id
                WHEN MATCHED THEN UPDATE SET
                    status = ?, requested_strategy = ?, worker_token = ?,
                    claimed_at = ?, completed_at = ?, error_code = ?, error_message = ?,
                    payload_json = ?
                WHEN NOT MATCHED THEN INSERT (
                    id, job_id, asset_id, command_type, requested_strategy, status,
                    idempotency_key, expected_state_version, actor, reason, payload_json,
                    worker_token, created_at, claimed_at, completed_at, error_code, error_message
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                );
                """,
                (
                    command.id,
                    command.status.value,
                    command.requested_strategy,
                    command.worker_token,
                    _utc(command.claimed_at),
                    _utc(command.completed_at),
                    command.error_code,
                    (command.error_message or None),
                    json.dumps(command.payload or {}, ensure_ascii=False),
                    command.id,
                    command.job_id,
                    command.asset_id,
                    command.command_type.value,
                    command.requested_strategy,
                    command.status.value,
                    command.idempotency_key,
                    command.expected_state_version,
                    command.actor,
                    command.reason,
                    json.dumps(command.payload or {}, ensure_ascii=False),
                    command.worker_token,
                    _utc(command.created_at),
                    _utc(command.claimed_at),
                    _utc(command.completed_at),
                    command.error_code,
                    command.error_message,
                ),
            )

    def get_by_id(self, command_id: str) -> AssetProcessingCommand | None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, job_id, asset_id, command_type, requested_strategy, status,
                       idempotency_key, expected_state_version, actor, reason, payload_json,
                       worker_token, created_at, claimed_at, completed_at, error_code, error_message
                FROM asset_processing_commands WHERE id = ?
                """,
                (command_id,),
            )
            row = cur.fetchone()
        return _row_to_cmd(row) if row else None

    def list_by_job_asset(
        self, job_id: str, asset_id: str, *, limit: int = 50
    ) -> Sequence[AssetProcessingCommand]:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT TOP (?) id, job_id, asset_id, command_type, requested_strategy, status,
                       idempotency_key, expected_state_version, actor, reason, payload_json,
                       worker_token, created_at, claimed_at, completed_at, error_code, error_message
                FROM asset_processing_commands
                WHERE job_id = ? AND asset_id = ?
                ORDER BY created_at DESC
                """,
                (int(limit), job_id, asset_id),
            )
            rows = cur.fetchall()
        return [_row_to_cmd(r) for r in rows]

    def try_claim(
        self,
        command_id: str,
        *,
        worker_token: str,
        now: datetime,
    ) -> AssetProcessingCommand | None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE asset_processing_commands
                SET status = 'CLAIMED', worker_token = ?, claimed_at = ?
                OUTPUT inserted.id, inserted.job_id, inserted.asset_id, inserted.command_type,
                       inserted.requested_strategy, inserted.status, inserted.idempotency_key,
                       inserted.expected_state_version, inserted.actor, inserted.reason,
                       inserted.payload_json, inserted.worker_token, inserted.created_at,
                       inserted.claimed_at, inserted.completed_at, inserted.error_code,
                       inserted.error_message
                WHERE id = ? AND status = 'QUEUED'
                """,
                (worker_token, _utc(now), command_id),
            )
            row = cur.fetchone()
        return _row_to_cmd(row) if row else None

    def try_claim_next_queued(
        self,
        *,
        worker_token: str,
        now: datetime,
        job_id: str | None = None,
    ) -> AssetProcessingCommand | None:
        with self._client.cursor() as cur:
            if job_id:
                cur.execute(
                    """
                    ;WITH cte AS (
                        SELECT TOP (1) id
                        FROM asset_processing_commands WITH (UPDLOCK, READPAST, ROWLOCK)
                        WHERE status = 'QUEUED' AND job_id = ?
                        ORDER BY created_at ASC
                    )
                    UPDATE c
                    SET status = 'CLAIMED', worker_token = ?, claimed_at = ?
                    OUTPUT inserted.id, inserted.job_id, inserted.asset_id, inserted.command_type,
                           inserted.requested_strategy, inserted.status, inserted.idempotency_key,
                           inserted.expected_state_version, inserted.actor, inserted.reason,
                           inserted.payload_json, inserted.worker_token, inserted.created_at,
                           inserted.claimed_at, inserted.completed_at, inserted.error_code,
                           inserted.error_message
                    FROM asset_processing_commands c
                    INNER JOIN cte ON c.id = cte.id
                    """,
                    (job_id, worker_token, _utc(now)),
                )
            else:
                cur.execute(
                    """
                    ;WITH cte AS (
                        SELECT TOP (1) id
                        FROM asset_processing_commands WITH (UPDLOCK, READPAST, ROWLOCK)
                        WHERE status = 'QUEUED'
                        ORDER BY created_at ASC
                    )
                    UPDATE c
                    SET status = 'CLAIMED', worker_token = ?, claimed_at = ?
                    OUTPUT inserted.id, inserted.job_id, inserted.asset_id, inserted.command_type,
                           inserted.requested_strategy, inserted.status, inserted.idempotency_key,
                           inserted.expected_state_version, inserted.actor, inserted.reason,
                           inserted.payload_json, inserted.worker_token, inserted.created_at,
                           inserted.claimed_at, inserted.completed_at, inserted.error_code,
                           inserted.error_message
                    FROM asset_processing_commands c
                    INNER JOIN cte ON c.id = cte.id
                    """,
                    (worker_token, _utc(now)),
                )
            row = cur.fetchone()
        return _row_to_cmd(row) if row else None

    def mark_running(self, command: AssetProcessingCommand, *, now: datetime) -> None:
        command.status = AssetProcessingCommandStatus.RUNNING
        self.save(command)

    def mark_finished(self, command: AssetProcessingCommand, *, now: datetime) -> None:
        command.completed_at = now
        self.save(command)


__all__ = ["SqlAssetProcessingCommandRepository"]
