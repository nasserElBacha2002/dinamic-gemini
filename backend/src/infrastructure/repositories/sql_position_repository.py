"""
SQL Server implementation of PositionRepository — v3.0 Épica 6.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from src.application.ports.contracts import POSITION_LIST_JOB_ID_UNSET, PositionListQuery
from src.application.ports.repositories import JOB_ID_FILTER_UNSET, PositionRepository
from src.database.sqlserver import SqlServerClient
from src.domain.positions.entities import Position, PositionReviewResolution, PositionStatus
from src.infrastructure.repositories.db_row_text import normalize_db_str

logger = logging.getLogger(__name__)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _parse_json(raw: object, context: str = "") -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        text = raw.strip()
    else:
        text = str(raw).strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("Invalid JSON in %s: %s", context or "position", e)
        return None
    if not isinstance(parsed, dict):
        logger.warning("JSON root is not an object in %s", context or "position")
        return None
    return parsed


def _status_from_row(row: Any, position_id: str = "?") -> PositionStatus:
    raw = getattr(row, "status", None)
    if raw is None:
        s = "detected"
    elif isinstance(raw, str):
        s = raw.strip() or "detected"
    else:
        s = str(raw).strip() or "detected"
    try:
        return PositionStatus(s)
    except ValueError:
        logger.warning("Invalid position status %r for position_id=%s", s, position_id)
        return PositionStatus.DETECTED


def _review_resolution_from_row(
    row: Any,
    position_id: str = "?",
) -> PositionReviewResolution | None:
    raw = getattr(row, "review_resolution", None)
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return PositionReviewResolution(str(raw).strip())
    except ValueError:
        logger.warning(
            "Invalid position review_resolution %r for position_id=%s",
            raw,
            position_id,
        )
        return None


def _row_to_position(row: Any) -> Position:
    pid = getattr(row, "id", "")
    created = _ensure_utc(getattr(row, "created_at", None))
    updated = _ensure_utc(getattr(row, "updated_at", None))
    if created is None or updated is None:
        raise ValueError("positions row missing required created_at/updated_at")
    return Position(
        id=pid,
        aisle_id=normalize_db_str(getattr(row, "aisle_id", None)),
        status=_status_from_row(row, pid),
        review_resolution=_review_resolution_from_row(row, pid),
        confidence=float(getattr(row, "confidence", 0)),
        needs_review=bool(getattr(row, "needs_review", False)),
        primary_evidence_id=getattr(row, "primary_evidence_id", None),
        created_at=created,
        updated_at=updated,
        detected_summary_json=_parse_json(
            getattr(row, "detected_summary_json", None), f"position id={pid}"
        ),
        corrected_summary_json=_parse_json(
            getattr(row, "corrected_summary_json", None), f"position id={pid}"
        ),
        corrected_position_code=getattr(row, "corrected_position_code", None),
        job_id=getattr(row, "job_id", None),
    )


class SqlPositionRepository(PositionRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def save(self, position: Position) -> None:
        if position.created_at is None or position.updated_at is None:
            raise ValueError("Position created_at and updated_at are required")
        created = _ensure_utc(position.created_at)
        updated = _ensure_utc(position.updated_at)
        det_json = (
            json.dumps(position.detected_summary_json, ensure_ascii=False)
            if position.detected_summary_json
            else None
        )
        corr_json = (
            json.dumps(position.corrected_summary_json, ensure_ascii=False)
            if position.corrected_summary_json
            else None
        )
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE positions
                SET aisle_id = ?, status = ?, review_resolution = ?, confidence = ?, needs_review = ?,
                    primary_evidence_id = ?, updated_at = ?, detected_summary_json = ?, corrected_summary_json = ?,
                    corrected_position_code = ?, job_id = ?
                WHERE id = ?
                """,
                (
                    position.aisle_id,
                    position.status.value,
                    position.review_resolution.value
                    if position.review_resolution is not None
                    else None,
                    position.confidence,
                    position.needs_review,
                    position.primary_evidence_id,
                    updated,
                    det_json,
                    corr_json,
                    position.corrected_position_code,
                    position.job_id,
                    position.id,
                ),
            )
            if cur.rowcount == 0:
                cur.execute(
                    """
                    INSERT INTO positions (id, aisle_id, status, review_resolution, confidence, needs_review, primary_evidence_id, created_at, updated_at, detected_summary_json, corrected_summary_json, corrected_position_code, job_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        position.id,
                        position.aisle_id,
                        position.status.value,
                        position.review_resolution.value
                        if position.review_resolution is not None
                        else None,
                        position.confidence,
                        position.needs_review,
                        position.primary_evidence_id,
                        created,
                        updated,
                        det_json,
                        corr_json,
                        position.corrected_position_code,
                        position.job_id,
                    ),
                )

    def get_by_id(self, position_id: str) -> Position | None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, aisle_id, status, review_resolution, confidence, needs_review, primary_evidence_id,
                       created_at, updated_at, detected_summary_json, corrected_summary_json, corrected_position_code, job_id
                FROM positions WHERE id = ?
                """,
                (position_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return _row_to_position(row)

    def list_by_aisle(
        self,
        aisle_id: str,
        status: str | None = None,
        needs_review: bool | None = None,
        min_confidence: float | None = None,
        sku_filter: str | None = None,
        page: int = 1,
        page_size: int = 25,
        sort_by: str = "created_at",
        sort_dir: str = "asc",
        job_id: str | None | object = JOB_ID_FILTER_UNSET,
    ) -> Sequence[Position]:
        conditions = ["p.aisle_id = ?"]
        params: list = [aisle_id]
        if job_id is not JOB_ID_FILTER_UNSET:
            if job_id is None:
                conditions.append("p.job_id IS NULL")
            else:
                conditions.append("p.job_id = ?")
                params.append(job_id)
        join_product_records = False
        if sku_filter is not None and str(sku_filter).strip():
            join_product_records = True
            conditions.append("pr.sku LIKE ?")
            params.append(f"%{sku_filter.strip()}%")
        if status is not None:
            conditions.append("p.status = ?")
            params.append(status)
        if needs_review is not None:
            conditions.append("p.needs_review = ?")
            params.append(needs_review)
        if min_confidence is not None:
            conditions.append("p.confidence >= ?")
            params.append(min_confidence)
        where = " AND ".join(conditions)
        offset = (page - 1) * page_size
        params.extend([offset, page_size])
        col_map = {
            "created_at": "p.created_at",
            "updated_at": "p.updated_at",
            "confidence": "p.confidence",
            "id": "p.id",
        }
        order_col = col_map.get((sort_by or "created_at").strip().lower(), "p.created_at")
        order_dir = "DESC" if (sort_dir or "asc").strip().lower() == "desc" else "ASC"
        order_clause = f"ORDER BY {order_col} {order_dir}, p.id ASC"
        if join_product_records:
            sql = f"""
                SELECT DISTINCT p.id, p.aisle_id, p.status, p.confidence, p.needs_review, p.primary_evidence_id,
                       p.review_resolution, p.created_at, p.updated_at, p.detected_summary_json, p.corrected_summary_json, p.corrected_position_code, p.job_id
                FROM positions p
                INNER JOIN product_records pr ON pr.position_id = p.id
                WHERE {where}
                {order_clause}
                OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
                """
        else:
            sql = f"""
                SELECT p.id, p.aisle_id, p.status, p.confidence, p.needs_review, p.primary_evidence_id,
                       p.review_resolution, p.created_at, p.updated_at, p.detected_summary_json, p.corrected_summary_json, p.corrected_position_code, p.job_id
                FROM positions p
                WHERE {where}
                {order_clause}
                OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
                """
        with self._client.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [_row_to_position(row) for row in rows]

    def list_by_aisle_query(
        self, aisle_id: str, query: PositionListQuery | None = None
    ) -> Sequence[Position]:
        q = query or PositionListQuery()
        repo_job_id: str | None | object = JOB_ID_FILTER_UNSET
        if q.job_id is not POSITION_LIST_JOB_ID_UNSET:
            repo_job_id = q.job_id
        return self.list_by_aisle(
            aisle_id,
            status=q.status,
            needs_review=q.needs_review,
            min_confidence=q.min_confidence,
            sku_filter=q.sku_filter,
            page=q.page,
            page_size=q.page_size,
            sort_by=q.sort_by,
            sort_dir=q.sort_dir,
            job_id=repo_job_id,
        )

    def list_by_aisles(self, aisle_ids: Sequence[str]) -> Sequence[Position]:
        if not aisle_ids:
            return []
        placeholders = ",".join("?" * len(aisle_ids))
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, aisle_id, status, confidence, needs_review, primary_evidence_id,
                       review_resolution, created_at, updated_at, detected_summary_json, corrected_summary_json, corrected_position_code, job_id
                FROM positions
                WHERE aisle_id IN ({placeholders})
                ORDER BY created_at ASC, id ASC
                """,
                list(aisle_ids),
            )
            rows = cur.fetchall()
        return [_row_to_position(row) for row in rows]
