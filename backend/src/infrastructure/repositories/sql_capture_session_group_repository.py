"""SQL Server implementation of CaptureSessionGroupRepository — G3 + G4."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from src.application.ports.capture_repositories import CaptureSessionGroupRepository, CaptureSessionGroupSummary
from src.application.services.capture_group_materialization_state import materialization_state_for_counts
from src.database.sqlserver import SqlServerClient
from src.domain.capture.entities import CaptureSessionGroup, CaptureSessionGroupAisleAssignmentStatus
from src.infrastructure.repositories.db_row_text import normalize_db_str, optional_nonempty_db_str


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _parse_assignment_status(raw: object) -> CaptureSessionGroupAisleAssignmentStatus:
    if raw is None:
        s = "unassigned"
    elif isinstance(raw, str):
        s = raw.strip().lower() or "unassigned"
    else:
        s = str(raw).strip().lower() or "unassigned"
    try:
        return CaptureSessionGroupAisleAssignmentStatus(s)
    except ValueError:
        return CaptureSessionGroupAisleAssignmentStatus.UNASSIGNED


def _row_to_group(row: object) -> CaptureSessionGroup:
    gid = normalize_db_str(getattr(row, "id", None))
    sid = normalize_db_str(getattr(row, "session_id", None))
    created = _ensure_utc(getattr(row, "created_at", None))
    if created is None:
        raise ValueError("group.created_at is required")
    algo = normalize_db_str(getattr(row, "algorithm_version", None))
    assigned_raw = getattr(row, "assigned_aisle_id", None)
    assigned_aisle = optional_nonempty_db_str(assigned_raw)
    assigned_at = _ensure_utc(getattr(row, "assigned_at", None))
    st = _parse_assignment_status(getattr(row, "assignment_status", None))
    return CaptureSessionGroup(
        id=gid,
        session_id=sid,
        group_index=int(getattr(row, "group_index", 0)),
        created_at=created,
        algorithm_version=algo,
        assigned_aisle_id=assigned_aisle,
        assignment_status=st,
        assigned_at=assigned_at,
    )


class SqlCaptureSessionGroupRepository(CaptureSessionGroupRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def delete_all_for_session(self, session_id: str) -> None:
        with self._client.cursor() as cur:
            cur.execute("DELETE FROM dbo.capture_session_groups WHERE session_id = ?", (session_id,))

    def count_groups_for_session(self, session_id: str) -> int:
        with self._client.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS n FROM dbo.capture_session_groups WHERE session_id = ?",
                (session_id,),
            )
            row = cur.fetchone()
        return int(getattr(row, "n", 0) or 0) if row is not None else 0

    def get_by_id_and_session(self, group_id: str, session_id: str) -> Optional[CaptureSessionGroup]:
        gid = (group_id or "").strip()
        sid = (session_id or "").strip()
        if not gid or not sid:
            return None
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, session_id, group_index, created_at, algorithm_version,
                       assigned_aisle_id, assignment_status, assigned_at
                FROM dbo.capture_session_groups
                WHERE id = ? AND session_id = ?
                """,
                (gid, sid),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return _row_to_group(row)

    def update(self, group: CaptureSessionGroup) -> None:
        assigned_at = _ensure_utc(group.assigned_at)
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE dbo.capture_session_groups
                SET assigned_aisle_id = ?,
                    assignment_status = ?,
                    assigned_at = ?
                WHERE id = ? AND session_id = ?
                """,
                (
                    group.assigned_aisle_id,
                    group.assignment_status.value,
                    assigned_at,
                    group.id,
                    group.session_id,
                ),
            )

    def insert(self, group: CaptureSessionGroup) -> None:
        created = _ensure_utc(group.created_at)
        if created is None:
            raise ValueError("CaptureSessionGroup.created_at is required")
        with self._client.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dbo.capture_session_groups (
                    id, session_id, group_index, created_at, algorithm_version,
                    assigned_aisle_id, assignment_status, assigned_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    group.id,
                    group.session_id,
                    int(group.group_index),
                    created,
                    group.algorithm_version,
                    group.assigned_aisle_id,
                    group.assignment_status.value,
                    _ensure_utc(group.assigned_at),
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
                    g.assigned_aisle_id,
                    g.assignment_status,
                    g.assigned_at,
                    COUNT(i.id) AS item_count,
                    MIN(COALESCE(i.adjusted_capture_time, i.effective_capture_time)) AS start_time,
                    MAX(COALESCE(i.adjusted_capture_time, i.effective_capture_time)) AS end_time
                FROM dbo.capture_session_groups g
                INNER JOIN dbo.capture_session_items i ON i.group_id = g.id
                WHERE g.session_id = ?
                GROUP BY
                    g.id, g.group_index, g.created_at, g.algorithm_version,
                    g.assigned_aisle_id, g.assignment_status, g.assigned_at
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
            gid = normalize_db_str(getattr(row, "group_id", None))
            if not gid:
                continue
            algo = normalize_db_str(getattr(row, "algorithm_version", None))
            if not algo:
                continue
            assigned_aisle_raw = getattr(row, "assigned_aisle_id", None)
            assigned_aisle = optional_nonempty_db_str(assigned_aisle_raw)
            assigned_at = _ensure_utc(getattr(row, "assigned_at", None))
            assignment_status = _parse_assignment_status(getattr(row, "assignment_status", None))
            imported_n = int(getattr(row, "imported_count", 0) or 0)
            linked_n = int(getattr(row, "linked_imported_count", 0) or 0)
            mat_state = materialization_state_for_counts(
                assignment_status=assignment_status.value,
                imported_count=imported_n,
                linked_imported_count=linked_n,
            )
            out.append(
                CaptureSessionGroupSummary(
                    group_id=gid,
                    group_index=int(getattr(row, "group_index", 0)),
                    item_count=int(getattr(row, "item_count", 0)),
                    start_time=st,
                    end_time=en,
                    algorithm_version=algo,
                    assigned_aisle_id=assigned_aisle,
                    assignment_status=assignment_status.value,
                    assigned_at=assigned_at,
                    materialization_state=mat_state,
                )
            )
        return tuple(out)
