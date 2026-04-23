"""SQL Server implementation of CaptureSessionGroupRepository — G3."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from src.application.ports.capture_repositories import CaptureSessionGroupRepository, CaptureSessionGroupSummary
from src.database.sqlserver import SqlServerClient
from src.domain.capture.entities import CaptureSessionGroup


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


class SqlCaptureSessionGroupRepository(CaptureSessionGroupRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def delete_all_for_session(self, session_id: str) -> None:
        with self._client.cursor() as cur:
            cur.execute("DELETE FROM dbo.capture_session_groups WHERE session_id = ?", (session_id,))

    def insert(self, group: CaptureSessionGroup) -> None:
        created = _ensure_utc(group.created_at)
        if created is None:
            raise ValueError("CaptureSessionGroup.created_at is required")
        with self._client.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dbo.capture_session_groups (id, session_id, group_index, created_at, algorithm_version)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    group.id,
                    group.session_id,
                    int(group.group_index),
                    created,
                    group.algorithm_version,
                ),
            )

    def list_summaries(self, session_id: str) -> tuple[CaptureSessionGroupSummary, ...]:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT
                    g.id AS group_id,
                    g.group_index,
                    g.algorithm_version,
                    COUNT(i.id) AS item_count,
                    MIN(COALESCE(i.adjusted_capture_time, i.effective_capture_time)) AS start_time,
                    MAX(COALESCE(i.adjusted_capture_time, i.effective_capture_time)) AS end_time
                FROM dbo.capture_session_groups g
                INNER JOIN dbo.capture_session_items i ON i.group_id = g.id
                WHERE g.session_id = ?
                GROUP BY g.id, g.group_index, g.created_at, g.algorithm_version
                ORDER BY g.group_index ASC
                """,
                (session_id,),
            )
            rows = cur.fetchall()
        out: list[CaptureSessionGroupSummary] = []
        for row in rows:
            st = _ensure_utc(getattr(row, "start_time", None))
            en = _ensure_utc(getattr(row, "end_time", None))
            if st is None or en is None:
                continue
            gid = (getattr(row, "group_id", None) or "").strip()
            if not gid:
                continue
            algo = (getattr(row, "algorithm_version", None) or "").strip()
            if not algo:
                continue
            out.append(
                CaptureSessionGroupSummary(
                    group_id=gid,
                    group_index=int(getattr(row, "group_index", 0)),
                    item_count=int(getattr(row, "item_count", 0)),
                    start_time=st,
                    end_time=en,
                    algorithm_version=algo,
                )
            )
        return tuple(out)
