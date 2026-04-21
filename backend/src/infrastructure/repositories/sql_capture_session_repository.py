"""SQL Server implementation of CaptureSessionRepository — Sprint 2."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Sequence

import pyodbc

from src.application.errors import OpenCaptureSessionExistsError
from src.application.ports.capture_repositories import CaptureSessionRepository
from src.database.sqlserver import SqlServerClient
from src.domain.capture.entities import CaptureSession, CaptureSessionStatus

logger = logging.getLogger(__name__)

_OPEN_STATUS_EXCLUSION = ("cancelled", "failed", "confirmed")


def _is_one_open_per_aisle_unique_violation(exc: pyodbc.IntegrityError) -> bool:
    msg = str(exc).lower()
    return "uq_capture_sessions_one_open_per_aisle" in msg or (
        "capture_sessions" in msg and "duplicate" in msg and "inventory_id" in msg
    )


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _status_from_row(raw: object, session_id: str) -> CaptureSessionStatus:
    s = (raw or "").strip().lower() if raw is not None else ""
    try:
        return CaptureSessionStatus(s)
    except ValueError:
        logger.warning("Invalid capture_sessions.status from DB: %r for id=%s", raw, session_id)
        return CaptureSessionStatus.DRAFT


def _row_to_session(row) -> CaptureSession:
    sid = getattr(row, "id", "") or ""
    created = _ensure_utc(getattr(row, "created_at", None))
    updated = _ensure_utc(getattr(row, "updated_at", None))
    if created is None or updated is None:
        raise ValueError(f"capture_sessions row {sid!r} missing created_at/updated_at")
    off_raw = getattr(row, "clock_offset_seconds", 0)
    try:
        clock_off = int(off_raw) if off_raw is not None else 0
    except (TypeError, ValueError):
        clock_off = 0
    return CaptureSession(
        id=sid,
        inventory_id=getattr(row, "inventory_id", "") or "",
        aisle_id=getattr(row, "aisle_id", "") or "",
        status=_status_from_row(getattr(row, "status", None), sid),
        created_at=created,
        updated_at=updated,
        opened_at=_ensure_utc(getattr(row, "opened_at", None)),
        closed_at=_ensure_utc(getattr(row, "closed_at", None)),
        clock_offset_seconds=clock_off,
    )


class SqlCaptureSessionRepository(CaptureSessionRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def save(self, session: CaptureSession) -> None:
        created = _ensure_utc(session.created_at)
        updated = _ensure_utc(session.updated_at)
        opened = _ensure_utc(session.opened_at)
        closed = _ensure_utc(session.closed_at)
        if created is None or updated is None:
            raise ValueError("CaptureSession.created_at and updated_at are required")
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE capture_sessions
                SET inventory_id = ?, aisle_id = ?, status = ?, created_at = ?, updated_at = ?,
                    opened_at = ?, closed_at = ?, clock_offset_seconds = ?
                WHERE id = ?
                """,
                (
                    session.inventory_id,
                    session.aisle_id,
                    session.status.value,
                    created,
                    updated,
                    opened,
                    closed,
                    int(session.clock_offset_seconds),
                    session.id,
                ),
            )
            if cur.rowcount == 0:
                try:
                    cur.execute(
                        """
                        INSERT INTO capture_sessions (
                            id, inventory_id, aisle_id, status, created_at, updated_at, opened_at, closed_at,
                            clock_offset_seconds
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            session.id,
                            session.inventory_id,
                            session.aisle_id,
                            session.status.value,
                            created,
                            updated,
                            opened,
                            closed,
                            int(session.clock_offset_seconds),
                        ),
                    )
                except pyodbc.IntegrityError as exc:
                    if _is_one_open_per_aisle_unique_violation(exc):
                        raise OpenCaptureSessionExistsError(
                            "An open capture session already exists for this aisle; close or cancel it first."
                        ) from exc
                    raise

    def get_by_id(self, session_id: str) -> Optional[CaptureSession]:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, inventory_id, aisle_id, status, created_at, updated_at, opened_at, closed_at,
                       clock_offset_seconds
                FROM capture_sessions WHERE id = ?
                """,
                (session_id,),
            )
            row = cur.fetchone()
        return _row_to_session(row) if row else None

    def get_by_id_for_inventory(self, session_id: str, inventory_id: str) -> Optional[CaptureSession]:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, inventory_id, aisle_id, status, created_at, updated_at, opened_at, closed_at,
                       clock_offset_seconds
                FROM capture_sessions WHERE id = ? AND inventory_id = ?
                """,
                (session_id, inventory_id),
            )
            row = cur.fetchone()
        return _row_to_session(row) if row else None

    def count_open_sessions_for_aisle(self, inventory_id: str, aisle_id: str) -> int:
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(1) AS c
                FROM capture_sessions
                WHERE inventory_id = ? AND aisle_id = ?
                  AND closed_at IS NULL
                  AND status NOT IN ({",".join("?" for _ in _OPEN_STATUS_EXCLUSION)})
                """,
                (inventory_id, aisle_id, *_OPEN_STATUS_EXCLUSION),
            )
            row = cur.fetchone()
        return int(getattr(row, "c", row[0]) if row else 0)

    def list_by_inventory(
        self,
        inventory_id: str,
        *,
        aisle_id: Optional[str] = None,
        statuses: Optional[Sequence[CaptureSessionStatus]] = None,
        created_from: Optional[datetime] = None,
        created_to: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 25,
    ) -> tuple[Sequence[CaptureSession], int]:
        page = max(1, page)
        page_size = max(1, page_size)
        offset = (page - 1) * page_size
        where_parts = ["inventory_id = ?"]
        params: list = [inventory_id]
        if aisle_id:
            where_parts.append("aisle_id = ?")
            params.append(aisle_id)
        if statuses is not None and len(statuses) > 0:
            placeholders = ",".join("?" * len(statuses))
            where_parts.append(f"status IN ({placeholders})")
            params.extend(s.value for s in statuses)
        if created_from is not None:
            where_parts.append("created_at >= ?")
            params.append(_ensure_utc(created_from))
        if created_to is not None:
            where_parts.append("created_at <= ?")
            params.append(_ensure_utc(created_to))
        where_sql = " AND ".join(where_parts)
        count_sql = f"SELECT COUNT(1) AS c FROM capture_sessions WHERE {where_sql}"
        list_sql = f"""
            SELECT id, inventory_id, aisle_id, status, created_at, updated_at, opened_at, closed_at,
                   clock_offset_seconds
            FROM capture_sessions
            WHERE {where_sql}
            ORDER BY created_at DESC, id DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """
        with self._client.cursor() as cur:
            cur.execute(count_sql, tuple(params))
            crow = cur.fetchone()
            total = int(getattr(crow, "c", crow[0]) if crow else 0)
            cur.execute(list_sql, tuple(params + [offset, page_size]))
            rows = cur.fetchall()
        return tuple(_row_to_session(r) for r in rows), total
