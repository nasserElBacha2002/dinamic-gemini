"""SQL Server ordered capture session repository."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

import pyodbc

from src.application.errors import OrderedCaptureSessionConflictError
from src.application.ports.ordered_capture_session_repository import (
    OrderedCaptureSessionRepository,
)
from src.database.sqlserver import SqlServerClient
from src.domain.ordered_capture.entities import (
    OrderedCaptureSession,
    OrderedCaptureSessionStatus,
)
from src.infrastructure.repositories.db_row_text import normalize_db_str, optional_nonempty_db_str


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _is_one_open_per_aisle_unique_violation(exc: pyodbc.IntegrityError) -> bool:
    return "uq_ordered_capture_sessions_one_open_per_aisle" in str(exc).lower()


def _row_to_session(row) -> OrderedCaptureSession:
    status_raw = normalize_db_str(getattr(row, "status", None)) or "OPEN"
    try:
        status = OrderedCaptureSessionStatus(status_raw)
    except ValueError:
        status = OrderedCaptureSessionStatus.OPEN
    created = _ensure_utc(getattr(row, "created_at", None))
    updated = _ensure_utc(getattr(row, "updated_at", None))
    if created is None or updated is None:
        raise ValueError("ordered_capture_sessions row missing timestamps")
    return OrderedCaptureSession(
        id=normalize_db_str(getattr(row, "id", None)),
        inventory_id=normalize_db_str(getattr(row, "inventory_id", None)),
        aisle_id=normalize_db_str(getattr(row, "aisle_id", None)),
        status=status,
        created_at=created,
        updated_at=updated,
        client_id=optional_nonempty_db_str(getattr(row, "client_id", None)),
        expected_asset_count=getattr(row, "expected_asset_count", None),
        uploaded_asset_count=int(getattr(row, "uploaded_asset_count", 0) or 0),
        sequence_version=int(getattr(row, "sequence_version", 1) or 1),
        created_by=optional_nonempty_db_str(getattr(row, "created_by", None)),
        sealed_at=_ensure_utc(getattr(row, "sealed_at", None)),
        processing_started_at=_ensure_utc(getattr(row, "processing_started_at", None)),
        completed_at=_ensure_utc(getattr(row, "completed_at", None)),
    )


_SELECT = """
SELECT id, client_id, inventory_id, aisle_id, status, expected_asset_count,
       uploaded_asset_count, sequence_version, created_by, created_at, updated_at,
       sealed_at, processing_started_at, completed_at
FROM ordered_capture_sessions
"""


class SqlOrderedCaptureSessionRepository(OrderedCaptureSessionRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def save(self, session: OrderedCaptureSession) -> None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE ordered_capture_sessions
                SET client_id = ?, inventory_id = ?, aisle_id = ?, status = ?,
                    expected_asset_count = ?, uploaded_asset_count = ?, sequence_version = ?,
                    created_by = ?, updated_at = ?, sealed_at = ?,
                    processing_started_at = ?, completed_at = ?
                WHERE id = ?
                """,
                (
                    session.client_id,
                    session.inventory_id,
                    session.aisle_id,
                    session.status.value,
                    session.expected_asset_count,
                    session.uploaded_asset_count,
                    session.sequence_version,
                    session.created_by,
                    _ensure_utc(session.updated_at),
                    _ensure_utc(session.sealed_at),
                    _ensure_utc(session.processing_started_at),
                    _ensure_utc(session.completed_at),
                    session.id,
                ),
            )
            if cur.rowcount == 0:
                try:
                    cur.execute(
                        """
                        INSERT INTO ordered_capture_sessions (
                            id, client_id, inventory_id, aisle_id, status,
                            expected_asset_count, uploaded_asset_count, sequence_version,
                            created_by, created_at, updated_at, sealed_at,
                            processing_started_at, completed_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            session.id,
                            session.client_id,
                            session.inventory_id,
                            session.aisle_id,
                            session.status.value,
                            session.expected_asset_count,
                            session.uploaded_asset_count,
                            session.sequence_version,
                            session.created_by,
                            _ensure_utc(session.created_at),
                            _ensure_utc(session.updated_at),
                            _ensure_utc(session.sealed_at),
                            _ensure_utc(session.processing_started_at),
                            _ensure_utc(session.completed_at),
                        ),
                    )
                except pyodbc.IntegrityError as exc:
                    if _is_one_open_per_aisle_unique_violation(exc):
                        raise OrderedCaptureSessionConflictError(
                            "An open ordered capture session already exists for this aisle",
                            code="ORDERED_CAPTURE_OPEN_SESSION_EXISTS",
                        ) from exc
                    raise

    def get_by_id(self, session_id: str) -> OrderedCaptureSession | None:
        with self._client.cursor() as cur:
            cur.execute(_SELECT + " WHERE id = ?", (session_id,))
            row = cur.fetchone()
        return _row_to_session(row) if row else None

    def list_by_aisle(
        self,
        aisle_id: str,
        *,
        statuses: Sequence[str] | None = None,
    ) -> list[OrderedCaptureSession]:
        with self._client.cursor() as cur:
            if statuses:
                placeholders = ",".join("?" * len(statuses))
                cur.execute(
                    _SELECT
                    + f" WHERE aisle_id = ? AND status IN ({placeholders})"
                    + " ORDER BY created_at DESC",  # nosec B608
                    [aisle_id, *[str(s).upper() for s in statuses]],
                )
            else:
                cur.execute(
                    _SELECT + " WHERE aisle_id = ? ORDER BY created_at DESC",
                    (aisle_id,),
                )
            rows = cur.fetchall()
        return [_row_to_session(r) for r in rows]

    def get_open_or_uploading_for_aisle(self, aisle_id: str) -> OrderedCaptureSession | None:
        with self._client.cursor() as cur:
            cur.execute(
                _SELECT
                + " WHERE aisle_id = ? AND status IN ('OPEN', 'UPLOADING')"
                + " ORDER BY updated_at DESC",
                (aisle_id,),
            )
            row = cur.fetchone()
        return _row_to_session(row) if row else None

    def get_or_create_open_for_aisle(
        self, session: OrderedCaptureSession
    ) -> OrderedCaptureSession:
        existing = self.get_open_or_uploading_for_aisle(session.aisle_id)
        if existing is not None:
            return existing
        try:
            self.save(session)
            return session
        except OrderedCaptureSessionConflictError:
            recovered = self.get_open_or_uploading_for_aisle(session.aisle_id)
            if recovered is not None:
                return recovered
            raise
