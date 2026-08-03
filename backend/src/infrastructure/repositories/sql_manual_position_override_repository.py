"""SQL Server repository for immutable manual position-override revisions."""

from __future__ import annotations

from dataclasses import replace
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

    def list_active_for_results(
        self, job_id: str, result_ids: list[str]
    ) -> dict[str, ManualProductPositionOverride]:
        ids = list(dict.fromkeys(result_id for result_id in result_ids if result_id))
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        with self._client.cursor() as cur:
            cur.execute(
                _SELECT
                + f" WHERE job_id = ? AND result_id IN ({placeholders}) AND is_active = 1",
                (job_id, *ids),
            )
            rows = [_row_to_entity(row) for row in cur.fetchall()]
        return {row.result_id: row for row in rows}

    def get_effective_versions(
        self, job_id: str, result_ids: list[str]
    ) -> dict[str, int]:
        ids = list(dict.fromkeys(result_id for result_id in result_ids if result_id))
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        with self._client.cursor() as cur:
            cur.execute(
                "SELECT result_id, version FROM dbo.product_position_effective_versions "
                + f"WHERE job_id = ? AND result_id IN ({placeholders})",
                (job_id, *ids),
            )
            rows = cur.fetchall()
        return {
            normalize_db_str(row.result_id): int(row.version)
            for row in rows
        }

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
        expected_effective_version: int,
        expected_automatic_reconciliation_id: str | None,
        expected_automatic_assignment_id: str | None,
        expected_active_override_id: str | None,
        expected_active_override_version: int | None,
    ) -> ManualProductPositionOverride:
        saved = revision
        try:
            with self._client.begin_transaction() as txn:
                cur = txn.connection.cursor()
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
                        txn.commit()
                        return existing
                    raise PositionOverrideIdempotencyConflictError(
                        "Idempotency key was reused with a different payload."
                    )
                cur.execute(
                    """
                    SELECT version
                    FROM dbo.product_position_effective_versions WITH (UPDLOCK, HOLDLOCK)
                    WHERE job_id = ? AND result_id = ?
                    """,
                    revision.job_id,
                    revision.result_id,
                )
                version_row = cur.fetchone()
                current_version = int(version_row.version) if version_row else 0
                if current_version != expected_effective_version:
                    raise PositionOverrideConflictError(
                        "The effective position changed.",
                        current_version=current_version,
                    )
                cur.execute(
                    """
                    SELECT TOP 1 id
                    FROM dbo.position_reconciliations WITH (UPDLOCK, HOLDLOCK)
                    WHERE job_id = ? AND is_active = 1 AND status = 'COMPLETED'
                    ORDER BY created_at DESC, id DESC
                    """,
                    revision.job_id,
                )
                reconciliation = cur.fetchone()
                current_reconciliation_id = (
                    optional_nonempty_db_str(reconciliation.id)
                    if reconciliation is not None
                    else None
                )
                cur.execute(
                    """
                    SELECT TOP 1 id, reconciliation_id
                    FROM dbo.product_position_assignments WITH (UPDLOCK, HOLDLOCK)
                    WHERE job_id = ? AND result_id = ? AND is_active = 1
                    ORDER BY created_at DESC, id DESC
                    """,
                    revision.job_id,
                    revision.result_id,
                )
                assignment = cur.fetchone()
                current_assignment_id = (
                    optional_nonempty_db_str(assignment.id)
                    if assignment is not None
                    and optional_nonempty_db_str(assignment.reconciliation_id)
                    == current_reconciliation_id
                    else None
                )
                current_automatic = (
                    current_reconciliation_id,
                    current_assignment_id,
                )
                if current_automatic != (
                    expected_automatic_reconciliation_id,
                    expected_automatic_assignment_id,
                ):
                    raise PositionOverrideConflictError(
                        "The automatic position assignment changed.",
                        current_version=current_version,
                    )
                cur.execute(
                    _SELECT
                    + " WITH (UPDLOCK, HOLDLOCK) WHERE job_id = ? AND result_id = ? AND is_active = 1",
                    revision.job_id,
                    revision.result_id,
                )
                active = cur.fetchone()
                current_active = (
                    (
                        optional_nonempty_db_str(active.id),
                        int(active.version),
                    )
                    if active is not None
                    else (None, None)
                )
                if current_active != (
                    expected_active_override_id,
                    expected_active_override_version,
                ):
                    raise PositionOverrideConflictError(
                        "The active manual override changed.",
                        current_version=current_version,
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
                next_version = current_version + 1
                saved = replace(revision, version=next_version)
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
                    saved.id,
                    saved.client_id,
                    saved.inventory_id,
                    saved.aisle_id,
                    saved.job_id,
                    saved.result_id,
                    saved.source_asset_id,
                    saved.automatic_assignment_id,
                    saved.automatic_reconciliation_id,
                    saved.previous_effective_position_label_id,
                    saved.new_position_label_id,
                    saved.new_position_name_snapshot,
                    saved.override_action.value,
                    saved.reason_code.value,
                    saved.reason_text,
                    saved.created_by_user_id,
                    saved.created_by_role,
                    saved.idempotency_key,
                    saved.version,
                    saved.is_active,
                    saved.superseded_override_id,
                    saved.created_at,
                    saved.updated_at,
                    saved.deactivated_at,
                )
                if version_row is None:
                    cur.execute(
                        """
                        INSERT INTO dbo.product_position_effective_versions
                            (job_id, result_id, version, updated_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        saved.job_id,
                        saved.result_id,
                        saved.version,
                        saved.updated_at,
                    )
                else:
                    cur.execute(
                        """
                        UPDATE dbo.product_position_effective_versions
                        SET version = ?, updated_at = ?
                        WHERE job_id = ? AND result_id = ?
                        """,
                        saved.version,
                        saved.updated_at,
                        saved.job_id,
                        saved.result_id,
                    )
                txn.commit()
        except pyodbc.IntegrityError as exc:
            if "uq_manual_position_override_idempotency" in str(exc).lower():
                raise PositionOverrideIdempotencyConflictError(
                    "Idempotency key was already used."
                ) from exc
            raise
        return saved
