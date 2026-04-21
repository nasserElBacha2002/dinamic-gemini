"""SQL Server implementation of CaptureSessionItemRepository — Sprint 2."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Sequence

import pyodbc

from src.application.errors import CaptureSessionDuplicateItemContentError
from src.application.ports.capture_repositories import CaptureSessionItemRepository
from src.database.sqlserver import SqlServerClient
from src.domain.capture.entities import (
    CaptureSessionItem,
    CaptureSessionItemAssignmentStatus,
    CaptureSessionItemImportStatus,
    CaptureTimeSource,
)

logger = logging.getLogger(__name__)


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _import_status_from_row(raw: object, item_id: str) -> CaptureSessionItemImportStatus:
    s = (raw or "").strip().lower() if raw is not None else ""
    try:
        return CaptureSessionItemImportStatus(s)
    except ValueError:
        logger.warning("Invalid capture_session_items.import_status: %r for id=%s", raw, item_id)
        return CaptureSessionItemImportStatus.PENDING_IMPORT


def _assignment_status_from_row(raw: object, item_id: str) -> CaptureSessionItemAssignmentStatus:
    s = (raw or "").strip().lower() if raw is not None else ""
    try:
        return CaptureSessionItemAssignmentStatus(s)
    except ValueError:
        logger.warning("Invalid capture_session_items.assignment_status: %r for id=%s", raw, item_id)
        return CaptureSessionItemAssignmentStatus.PENDING


def _time_source_from_row(raw: object) -> Optional[CaptureTimeSource]:
    if raw is None or not str(raw).strip():
        return None
    try:
        return CaptureTimeSource(str(raw).strip().lower())
    except ValueError:
        return None


def _is_session_content_hash_unique_violation(exc: pyodbc.IntegrityError) -> bool:
    """Detect duplicate (session_id, content_hash) insert on filtered unique index."""
    msg = str(exc).lower()
    return "uq_capture_session_items_session_content_hash" in msg or (
        "unique" in msg and "capture_session_items" in msg and "content_hash" in msg
    )


def _row_to_item(row) -> CaptureSessionItem:
    iid = getattr(row, "id", "") or ""
    updated = _ensure_utc(getattr(row, "updated_at", None))
    if updated is None:
        raise ValueError(f"capture_session_items row {iid!r} missing updated_at")
    return CaptureSessionItem(
        id=iid,
        session_id=getattr(row, "session_id", "") or "",
        staging_storage_key=(getattr(row, "staging_storage_key", None) or "").strip(),
        import_status=_import_status_from_row(getattr(row, "import_status", None), iid),
        assignment_status=_assignment_status_from_row(getattr(row, "assignment_status", None), iid),
        updated_at=updated,
        content_hash=(getattr(row, "content_hash", None) or "").strip() or None,
        effective_capture_time=_ensure_utc(getattr(row, "effective_capture_time", None)),
        time_source=_time_source_from_row(getattr(row, "time_source", None)),
        time_confidence=getattr(row, "time_confidence", None),
        linked_source_asset_id=(getattr(row, "linked_source_asset_id", None) or "").strip() or None,
        last_error_code=(getattr(row, "last_error_code", None) or "").strip() or None,
        last_error_detail=(getattr(row, "last_error_detail", None) or "").strip() or None,
        original_filename=(getattr(row, "original_filename", None) or "").strip() or None,
        adjusted_capture_time=_ensure_utc(getattr(row, "adjusted_capture_time", None)),
        assignment_reason=(getattr(row, "assignment_reason", None) or "").strip() or None,
        preview_target_position_id=(getattr(row, "preview_target_position_id", None) or "").strip() or None,
    )


class SqlCaptureSessionItemRepository(CaptureSessionItemRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def save(self, item: CaptureSessionItem) -> None:
        updated = _ensure_utc(item.updated_at)
        if updated is None:
            raise ValueError("CaptureSessionItem.updated_at is required")
        eff = _ensure_utc(item.effective_capture_time)
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE capture_session_items
                SET session_id = ?, staging_storage_key = ?, content_hash = ?,
                    effective_capture_time = ?, time_source = ?, time_confidence = ?,
                    import_status = ?, assignment_status = ?, linked_source_asset_id = ?,
                    last_error_code = ?, last_error_detail = ?, updated_at = ?, original_filename = ?,
                    adjusted_capture_time = ?, assignment_reason = ?, preview_target_position_id = ?
                WHERE id = ?
                """,
                (
                    item.session_id,
                    item.staging_storage_key,
                    item.content_hash,
                    eff,
                    item.time_source.value if item.time_source else None,
                    item.time_confidence,
                    item.import_status.value,
                    item.assignment_status.value,
                    item.linked_source_asset_id,
                    item.last_error_code,
                    item.last_error_detail,
                    updated,
                    item.original_filename,
                    _ensure_utc(item.adjusted_capture_time),
                    item.assignment_reason,
                    item.preview_target_position_id,
                    item.id,
                ),
            )
            if cur.rowcount == 0:
                try:
                    cur.execute(
                        """
                        INSERT INTO capture_session_items (
                            id, session_id, staging_storage_key, content_hash,
                            effective_capture_time, time_source, time_confidence,
                            import_status, assignment_status, linked_source_asset_id,
                            last_error_code, last_error_detail, updated_at, original_filename,
                            adjusted_capture_time, assignment_reason, preview_target_position_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            item.id,
                            item.session_id,
                            item.staging_storage_key,
                            item.content_hash,
                            eff,
                            item.time_source.value if item.time_source else None,
                            item.time_confidence,
                            item.import_status.value,
                            item.assignment_status.value,
                            item.linked_source_asset_id,
                            item.last_error_code,
                            item.last_error_detail,
                            updated,
                            item.original_filename,
                            _ensure_utc(item.adjusted_capture_time),
                            item.assignment_reason,
                            item.preview_target_position_id,
                        ),
                    )
                except pyodbc.IntegrityError as exc:
                    if _is_session_content_hash_unique_violation(exc):
                        raise CaptureSessionDuplicateItemContentError(
                            "Duplicate file content in this capture session"
                        ) from exc
                    raise

    def get_by_id(self, item_id: str) -> Optional[CaptureSessionItem]:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, session_id, staging_storage_key, content_hash,
                       effective_capture_time, time_source, time_confidence,
                       import_status, assignment_status, linked_source_asset_id,
                       last_error_code, last_error_detail, updated_at, original_filename,
                       adjusted_capture_time, assignment_reason, preview_target_position_id
                FROM capture_session_items WHERE id = ?
                """,
                (item_id,),
            )
            row = cur.fetchone()
        return _row_to_item(row) if row else None

    def list_by_session(self, session_id: str) -> Sequence[CaptureSessionItem]:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, session_id, staging_storage_key, content_hash,
                       effective_capture_time, time_source, time_confidence,
                       import_status, assignment_status, linked_source_asset_id,
                       last_error_code, last_error_detail, updated_at, original_filename,
                       adjusted_capture_time, assignment_reason, preview_target_position_id
                FROM capture_session_items
                WHERE session_id = ?
                ORDER BY updated_at ASC, id ASC
                """,
                (session_id,),
            )
            rows = cur.fetchall()
        return tuple(_row_to_item(r) for r in rows)

    def list_staging_cleanup_candidates(self, session_id: str) -> Sequence[CaptureSessionItem]:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, session_id, staging_storage_key, content_hash,
                       effective_capture_time, time_source, time_confidence,
                       import_status, assignment_status, linked_source_asset_id,
                       last_error_code, last_error_detail, updated_at, original_filename,
                       adjusted_capture_time, assignment_reason, preview_target_position_id
                FROM capture_session_items
                WHERE session_id = ?
                  AND linked_source_asset_id IS NULL
                  AND LTRIM(RTRIM(staging_storage_key)) <> ''
                """,
                (session_id,),
            )
            rows = cur.fetchall()
        return tuple(_row_to_item(r) for r in rows)

    def has_item_with_content_hash(self, session_id: str, content_hash: str) -> bool:
        h = (content_hash or "").strip()
        if not h:
            return False
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM capture_session_items
                WHERE session_id = ? AND content_hash = ?
                """,
                (session_id, h),
            )
            return cur.fetchone() is not None

    def count_items_with_import_status(
        self, session_id: str, import_status: CaptureSessionItemImportStatus
    ) -> int:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(1) AS c
                FROM capture_session_items
                WHERE session_id = ? AND import_status = ?
                """,
                (session_id, import_status.value),
            )
            row = cur.fetchone()
        return int(getattr(row, "c", row[0]) if row else 0)