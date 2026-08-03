"""SQL Server repository for Phase 4 reconciliation revisions."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from src.application.errors import (
    PositionReconciliationConcurrentUpdateError,
    PositionReconciliationInputChangedError,
)
from src.database.sqlserver import SqlServerClient
from src.domain.position_reconciliation.entities import (
    AssignmentSource,
    AssignmentStatus,
    PositionReconciliation,
    ProductPositionAssignment,
    ReconciliationStatus,
)
from src.infrastructure.repositories.db_row_text import normalize_db_str, optional_nonempty_db_str

_RECONCILIATION_SELECT = """
SELECT id, client_id, inventory_id, job_id, ordered_capture_session_id,
       reconciliation_name, reconciliation_version, input_fingerprint, status,
       started_at, completed_at, failure_code, attempt_count, assigned_count,
       unassigned_count, sequence_gap_count, metadata_json, is_active,
       created_at, updated_at, superseded_at
FROM dbo.position_reconciliations
"""

_ASSIGNMENT_SELECT = """
SELECT id, client_id, inventory_id, job_id, result_id, source_asset_id,
       ordered_capture_session_id, sequence_number, position_label_id,
       position_name_snapshot, source_detection_id, assignment_status,
       assignment_reason, assignment_source, reconciliation_id,
       reconciliation_version, is_active, created_at, updated_at, superseded_at
FROM dbo.product_position_assignments
"""


def _utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def _metadata(raw: object) -> dict[str, Any]:
    if raw is None:
        return {}
    value = json.loads(str(raw))
    return value if isinstance(value, dict) else {}


def _reconciliation(row: Any) -> PositionReconciliation:
    return PositionReconciliation(
        id=normalize_db_str(row.id),
        client_id=normalize_db_str(row.client_id),
        inventory_id=normalize_db_str(row.inventory_id),
        job_id=normalize_db_str(row.job_id),
        ordered_capture_session_id=optional_nonempty_db_str(row.ordered_capture_session_id),
        reconciliation_name=normalize_db_str(row.reconciliation_name),
        reconciliation_version=normalize_db_str(row.reconciliation_version),
        input_fingerprint=normalize_db_str(row.input_fingerprint),
        status=ReconciliationStatus(normalize_db_str(row.status)),
        started_at=_utc(row.started_at),  # type: ignore[arg-type]
        completed_at=_utc(row.completed_at),
        failure_code=optional_nonempty_db_str(row.failure_code),
        attempt_count=int(row.attempt_count),
        assigned_count=int(row.assigned_count),
        unassigned_count=int(row.unassigned_count),
        sequence_gap_count=int(row.sequence_gap_count),
        metadata_json=_metadata(row.metadata_json),
        is_active=bool(row.is_active),
        created_at=_utc(row.created_at),  # type: ignore[arg-type]
        updated_at=_utc(row.updated_at),  # type: ignore[arg-type]
        superseded_at=_utc(row.superseded_at),
    )


def _assignment(row: Any) -> ProductPositionAssignment:
    source = optional_nonempty_db_str(row.assignment_source)
    return ProductPositionAssignment(
        id=normalize_db_str(row.id),
        client_id=normalize_db_str(row.client_id),
        inventory_id=normalize_db_str(row.inventory_id),
        job_id=normalize_db_str(row.job_id),
        result_id=normalize_db_str(row.result_id),
        source_asset_id=normalize_db_str(row.source_asset_id),
        ordered_capture_session_id=optional_nonempty_db_str(row.ordered_capture_session_id),
        sequence_number=int(row.sequence_number) if row.sequence_number is not None else None,
        position_label_id=optional_nonempty_db_str(row.position_label_id),
        position_name_snapshot=optional_nonempty_db_str(row.position_name_snapshot),
        source_detection_id=optional_nonempty_db_str(row.source_detection_id),
        assignment_status=AssignmentStatus(normalize_db_str(row.assignment_status)),
        assignment_reason=normalize_db_str(row.assignment_reason),
        assignment_source=AssignmentSource(source) if source else None,
        reconciliation_id=normalize_db_str(row.reconciliation_id),
        reconciliation_version=normalize_db_str(row.reconciliation_version),
        is_active=bool(row.is_active),
        created_at=_utc(row.created_at),  # type: ignore[arg-type]
        updated_at=_utc(row.updated_at),  # type: ignore[arg-type]
        superseded_at=_utc(row.superseded_at),
    )


def _insert_reconciliation(cur: Any, row: PositionReconciliation) -> None:
    cur.execute(
        """
        INSERT INTO dbo.position_reconciliations (
            id, client_id, inventory_id, job_id, ordered_capture_session_id,
            reconciliation_name, reconciliation_version, input_fingerprint, status,
            started_at, completed_at, failure_code, attempt_count, assigned_count,
            unassigned_count, sequence_gap_count, metadata_json, is_active,
            created_at, updated_at, superseded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row.id,
            row.client_id,
            row.inventory_id,
            row.job_id,
            row.ordered_capture_session_id,
            row.reconciliation_name,
            row.reconciliation_version,
            row.input_fingerprint,
            row.status.value,
            row.started_at,
            row.completed_at,
            row.failure_code,
            row.attempt_count,
            row.assigned_count,
            row.unassigned_count,
            row.sequence_gap_count,
            json.dumps(row.metadata_json, separators=(",", ":")) if row.metadata_json else None,
            row.is_active,
            row.created_at,
            row.updated_at,
            row.superseded_at,
        ),
    )


class SqlPositionReconciliationRepository:
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def get_published_by_job(self, job_id: str) -> PositionReconciliation | None:
        with self._client.cursor() as cur:
            cur.execute(
                _RECONCILIATION_SELECT
                + " WHERE job_id = ? AND is_active = 1 AND status = 'COMPLETED'",
                (job_id,),
            )
            row = cur.fetchone()
            return _reconciliation(row) if row else None

    def get_active_by_job(self, job_id: str) -> PositionReconciliation | None:
        return self.get_published_by_job(job_id)

    def get_last_attempt_by_job(self, job_id: str) -> PositionReconciliation | None:
        with self._client.cursor() as cur:
            cur.execute(
                "SELECT TOP 1 " + _RECONCILIATION_SELECT.split("SELECT ", 1)[1]
                + " WHERE job_id = ? ORDER BY created_at DESC, id DESC",
                (job_id,),
            )
            row = cur.fetchone()
            return _reconciliation(row) if row else None

    def get_by_id(self, reconciliation_id: str) -> PositionReconciliation | None:
        with self._client.cursor() as cur:
            cur.execute(_RECONCILIATION_SELECT + " WHERE id = ?", (reconciliation_id,))
            row = cur.fetchone()
            return _reconciliation(row) if row else None

    def mark_stale(self, job_id: str) -> PositionReconciliation | None:
        """Deprecated: publication remains active until a replacement is published."""
        return self.get_published_by_job(job_id)

    def begin_or_get_running(
        self, reconciliation: PositionReconciliation
    ) -> PositionReconciliation:
        with self._client.begin_transaction() as txn:
            cur = txn.connection.cursor()
            cur.execute(
                _RECONCILIATION_SELECT
                + " WITH (UPDLOCK, HOLDLOCK) WHERE job_id = ? AND is_active = 1",
                (reconciliation.job_id,),
            )
            row = cur.fetchone()
            if row is not None:
                published = _reconciliation(row)
                if (
                    published.status is ReconciliationStatus.COMPLETED
                    and published.input_fingerprint == reconciliation.input_fingerprint
                ):
                    txn.commit()
                    return published
                if published.status is not ReconciliationStatus.COMPLETED:
                    cur.execute(
                        "UPDATE dbo.position_reconciliations SET is_active = 0, "
                        "superseded_at = ?, updated_at = ? WHERE id = ?",
                        (
                            reconciliation.started_at,
                            reconciliation.started_at,
                            published.id,
                        ),
                    )
            cur.execute(
                _RECONCILIATION_SELECT
                + " WITH (UPDLOCK, HOLDLOCK) WHERE job_id = ? AND status = 'RUNNING' "
                "AND input_fingerprint = ? ORDER BY created_at DESC",
                (reconciliation.job_id, reconciliation.input_fingerprint),
            )
            running_row = cur.fetchone()
            if running_row is not None:
                txn.commit()
                return _reconciliation(running_row)
            reconciliation.is_active = False
            _insert_reconciliation(cur, reconciliation)
            txn.commit()
            return reconciliation

    def record_failed_attempt(
        self, attempt: PositionReconciliation
    ) -> PositionReconciliation:
        attempt.status = ReconciliationStatus.FAILED
        attempt.is_active = False
        with self._client.begin_transaction() as txn:
            cur = txn.connection.cursor()
            cur.execute(
                "SELECT id FROM dbo.position_reconciliations WITH (UPDLOCK, HOLDLOCK) WHERE id = ?",
                (attempt.id,),
            )
            if cur.fetchone() is None:
                _insert_reconciliation(cur, attempt)
            else:
                cur.execute(
                    "UPDATE dbo.position_reconciliations SET status = 'FAILED', failure_code = ?, "
                    "completed_at = ?, metadata_json = ?, is_active = 0, updated_at = ? WHERE id = ?",
                    (
                        attempt.failure_code,
                        attempt.completed_at,
                        json.dumps(attempt.metadata_json, separators=(",", ":"))
                        if attempt.metadata_json
                        else None,
                        attempt.updated_at,
                        attempt.id,
                    ),
                )
            txn.commit()
        return attempt

    def publish_completed_revision_atomically(
        self,
        reconciliation: PositionReconciliation,
        assignments: Sequence[ProductPositionAssignment],
        previous_active_id: str | None,
        expected_input_fingerprint: str,
    ) -> PositionReconciliation:
        if reconciliation.input_fingerprint != expected_input_fingerprint:
            raise PositionReconciliationInputChangedError(
                "Reconciliation fingerprint changed before publication"
            )
        with self._client.begin_transaction() as txn:
            cur = txn.connection.cursor()
            now = reconciliation.updated_at
            cur.execute(
                _RECONCILIATION_SELECT
                + " WITH (UPDLOCK, HOLDLOCK) WHERE job_id = ? AND is_active = 1",
                (reconciliation.job_id,),
            )
            active_row = cur.fetchone()
            active = _reconciliation(active_row) if active_row else None
            if active is not None and active.input_fingerprint == expected_input_fingerprint:
                txn.commit()
                return active
            active_id = active.id if active else None
            if active_id != previous_active_id:
                raise PositionReconciliationConcurrentUpdateError(
                    "Published reconciliation changed during processing"
                )
            if active is not None:
                cur.execute(
                    "UPDATE dbo.position_reconciliations SET is_active = 0, superseded_at = ?, "
                    "updated_at = ? WHERE id = ?",
                    (now, now, active.id),
                )
            cur.execute(
                "UPDATE dbo.product_position_assignments SET is_active = 0, superseded_at = ?, "
                "updated_at = ? WHERE job_id = ? AND is_active = 1",
                (now, now, reconciliation.job_id),
            )
            cur.execute(
                "SELECT id FROM dbo.position_reconciliations WHERE id = ?", (reconciliation.id,)
            )
            if cur.fetchone() is None:
                _insert_reconciliation(cur, reconciliation)
            else:
                cur.execute(
                    """
                    UPDATE dbo.position_reconciliations
                    SET input_fingerprint = ?, status = ?, completed_at = ?, failure_code = ?,
                        attempt_count = ?, assigned_count = ?, unassigned_count = ?,
                        sequence_gap_count = ?, metadata_json = ?, is_active = 1,
                        updated_at = ?, superseded_at = NULL
                    WHERE id = ?
                    """,
                    (
                        reconciliation.input_fingerprint,
                        reconciliation.status.value,
                        reconciliation.completed_at,
                        reconciliation.failure_code,
                        reconciliation.attempt_count,
                        reconciliation.assigned_count,
                        reconciliation.unassigned_count,
                        reconciliation.sequence_gap_count,
                        (
                            json.dumps(reconciliation.metadata_json, separators=(",", ":"))
                            if reconciliation.metadata_json
                            else None
                        ),
                        now,
                        reconciliation.id,
                    ),
                )
            for row in assignments:
                cur.execute(
                    """
                    INSERT INTO dbo.product_position_assignments (
                        id, client_id, inventory_id, job_id, result_id, source_asset_id,
                        ordered_capture_session_id, sequence_number, position_label_id,
                        position_name_snapshot, source_detection_id, assignment_status,
                        assignment_reason, assignment_source, reconciliation_id,
                        reconciliation_version, is_active, created_at, updated_at, superseded_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row.id,
                        row.client_id,
                        row.inventory_id,
                        row.job_id,
                        row.result_id,
                        row.source_asset_id,
                        row.ordered_capture_session_id,
                        row.sequence_number,
                        row.position_label_id,
                        row.position_name_snapshot,
                        row.source_detection_id,
                        row.assignment_status.value,
                        row.assignment_reason,
                        row.assignment_source.value if row.assignment_source else None,
                        row.reconciliation_id,
                        row.reconciliation_version,
                        row.is_active,
                        row.created_at,
                        row.updated_at,
                        row.superseded_at,
                    ),
                )
            txn.commit()
        return reconciliation

    def persist_revision_atomically(
        self,
        reconciliation: PositionReconciliation,
        assignments: Sequence[ProductPositionAssignment],
        previous_active_id: str | None,
    ) -> PositionReconciliation:
        return self.publish_completed_revision_atomically(
            reconciliation,
            assignments,
            previous_active_id,
            reconciliation.input_fingerprint,
        )

    def list_active_assignments(self, job_id: str) -> list[ProductPositionAssignment]:
        with self._client.cursor() as cur:
            cur.execute(
                _ASSIGNMENT_SELECT + " WHERE job_id = ? AND is_active = 1 "
                "ORDER BY CASE WHEN sequence_number IS NULL THEN 1 ELSE 0 END, sequence_number, result_id",
                (job_id,),
            )
            return [_assignment(row) for row in cur.fetchall()]

    def list_result_assignment_history(
        self, job_id: str, result_id: str
    ) -> list[ProductPositionAssignment]:
        with self._client.cursor() as cur:
            cur.execute(
                _ASSIGNMENT_SELECT
                + " WHERE job_id = ? AND result_id = ? ORDER BY created_at DESC, id DESC",
                (job_id, result_id),
            )
            return [_assignment(row) for row in cur.fetchall()]

    def list_unassigned(self, job_id: str) -> list[ProductPositionAssignment]:
        with self._client.cursor() as cur:
            cur.execute(
                _ASSIGNMENT_SELECT
                + " WHERE job_id = ? AND is_active = 1 AND assignment_status <> 'ASSIGNED_AUTOMATIC' "
                "ORDER BY CASE WHEN sequence_number IS NULL THEN 1 ELSE 0 END, sequence_number, result_id",
                (job_id,),
            )
            return [_assignment(row) for row in cur.fetchall()]
