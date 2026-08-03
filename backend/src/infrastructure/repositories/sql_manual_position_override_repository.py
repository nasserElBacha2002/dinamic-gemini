"""SQL Server repository for immutable manual position-override revisions."""

from __future__ import annotations

from datetime import timezone

import pyodbc

from src.application.position_override_errors import (
    PositionOverrideConflictError,
    PositionOverrideIdempotencyConflictError,
)
from src.database.sqlserver import SqlServerClient
from src.domain.position_overrides.entities import (
    ManualProductPositionOverride,
    PositionOverrideAction,
    PositionOverrideReasonCode,
)
from src.infrastructure.repositories.db_row_text import (
    normalize_db_str,
    optional_nonempty_db_str,
)

_SELECT = """
SELECT id, client_id, inventory_id, aisle_id, job_id, result_id, source_asset_id,
       automatic_assignment_id, automatic_reconciliation_id,
       previous_effective_position_label_id, new_position_label_id,
       new_position_name_snapshot, override_action, reason_code, reason_text,
       created_by_user_id, created_by_role, idempotency_key, version, is_active,
       superseded_override_id, created_at, updated_at, deactivated_at
FROM manual_product_position_overrides
"""


def _utc(value):
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def _row_to_entity(row) -> ManualProductPositionOverride:
    return ManualProductPositionOverride(
        id=normalize_db_str(row.id),
        client_id=normalize_db_str(row.client_id),
        inventory_id=normalize_db_str(row.inventory_id),
        aisle_id=normalize_db_str(row.aisle_id),
        job_id=normalize_db_str(row.job_id),
        result_id=normalize_db_str(row.result_id),
        source_asset_id=optional_nonempty_db_str(row.source_asset_id),
        automatic_assignment_id=optional_nonempty_db_str(row.automatic_assignment_id),
        automatic_reconciliation_id=optional_nonempty_db_str(row.automatic_reconciliation_id),
        previous_effective_position_label_id=optional_nonempty_db_str(
            row.previous_effective_position_label_id
        ),
        new_position_label_id=optional_nonempty_db_str(row.new_position_label_id),
        new_position_name_snapshot=optional_nonempty_db_str(row.new_position_name_snapshot),
        override_action=PositionOverrideAction(normalize_db_str(row.override_action)),
        reason_code=PositionOverrideReasonCode(normalize_db_str(row.reason_code)),
        reason_text=optional_nonempty_db_str(row.reason_text),
        created_by_user_id=normalize_db_str(row.created_by_user_id),
        created_by_role=normalize_db_str(row.created_by_role),
        idempotency_key=normalize_db_str(row.idempotency_key),
        version=int(row.version),
        is_active=bool(row.is_active),
        superseded_override_id=optional_nonempty_db_str(row.superseded_override_id),
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
        deactivated_at=_utc(row.deactivated_at),
    )


class SqlManualPositionOverrideRepository:
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def get_active(
        self, job_id: str, result_id: str
    ) -> ManualProductPositionOverride | None:
        with self._client.cursor() as cur:
            cur.execute(_SELECT + " WHERE job_id = ? AND result_id = ? AND is_active = 1", job_id, result_id)
            row = cur.fetchone()
        return _row_to_entity(row) if row else None

    def list_history(
        self, job_id: str, result_id: str
    ) -> list[ManualProductPositionOverride]:
        with self._client.cursor() as cur:
            cur.execute(
                _SELECT
                + " WHERE job_id = ? AND result_id = ? ORDER BY version DESC, created_at DESC",
                job_id,
                result_id,
            )
            rows = cur.fetchall()
        return [_row_to_entity(row) for row in rows]

    def get_by_idempotency_key(
        self, client_id: str, idempotency_key: str
    ) -> ManualProductPositionOverride | None:
        with self._client.cursor() as cur:
            cur.execute(
                _SELECT + " WHERE client_id = ? AND idempotency_key = ?",
                client_id,
                idempotency_key,
            )
            row = cur.fetchone()
        return _row_to_entity(row) if row else None

    def insert_revision_atomically(
        self,
        revision: ManualProductPositionOverride,
        *,
        expected_active_version: int,
    ) -> ManualProductPositionOverride:
        try:
            with self._client.cursor() as cur:
                cur.execute(
                    _SELECT
                    + " WITH (UPDLOCK, HOLDLOCK) WHERE client_id = ? AND idempotency_key = ?",
                    revision.client_id,
                    revision.idempotency_key,
                )
                replay = cur.fetchone()
                if replay is not None:
                    existing = _row_to_entity(replay)
                    if (
                        existing.job_id == revision.job_id
                        and existing.result_id == revision.result_id
                        and existing.override_action is revision.override_action
                        and existing.new_position_label_id
                        == revision.new_position_label_id
                        and existing.reason_code is revision.reason_code
                        and existing.reason_text == revision.reason_text
                    ):
                        return existing
                    raise PositionOverrideIdempotencyConflictError(
                        "Idempotency key was reused with a different payload."
                    )
                cur.execute(
                    _SELECT
                    + " WITH (UPDLOCK, HOLDLOCK) WHERE job_id = ? AND result_id = ? AND is_active = 1",
                    revision.job_id,
                    revision.result_id,
                )
                active = cur.fetchone()
                current = int(active.version) if active else 0
                if current != expected_active_version:
                    raise PositionOverrideConflictError(
                        "The effective position changed.", current_version=current
                    )
                if active is not None:
                    cur.execute(
                        """
                        UPDATE manual_product_position_overrides
                        SET is_active = 0, updated_at = ?, deactivated_at = ?
                        WHERE id = ? AND is_active = 1
                        """,
                        revision.created_at,
                        revision.created_at,
                        active.id,
                    )
                cur.execute(
                    """
                    INSERT INTO manual_product_position_overrides (
                        id, client_id, inventory_id, aisle_id, job_id, result_id,
                        source_asset_id, automatic_assignment_id, automatic_reconciliation_id,
                        previous_effective_position_label_id, new_position_label_id,
                        new_position_name_snapshot, override_action, reason_code, reason_text,
                        created_by_user_id, created_by_role, idempotency_key, version,
                        is_active, superseded_override_id, created_at, updated_at, deactivated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    revision.id,
                    revision.client_id,
                    revision.inventory_id,
                    revision.aisle_id,
                    revision.job_id,
                    revision.result_id,
                    revision.source_asset_id,
                    revision.automatic_assignment_id,
                    revision.automatic_reconciliation_id,
                    revision.previous_effective_position_label_id,
                    revision.new_position_label_id,
                    revision.new_position_name_snapshot,
                    revision.override_action.value,
                    revision.reason_code.value,
                    revision.reason_text,
                    revision.created_by_user_id,
                    revision.created_by_role,
                    revision.idempotency_key,
                    revision.version,
                    revision.is_active,
                    revision.superseded_override_id,
                    revision.created_at,
                    revision.updated_at,
                    revision.deactivated_at,
                )
        except pyodbc.IntegrityError as exc:
            if "uq_manual_position_override_idempotency" in str(exc).lower():
                raise PositionOverrideIdempotencyConflictError(
                    "Idempotency key was already used."
                ) from exc
            raise
        return revision
