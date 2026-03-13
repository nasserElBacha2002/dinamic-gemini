"""
SQL Server implementation of PositionRepository — v3.0 Épica 6.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence

from src.application.ports.contracts import PositionListQuery
from src.application.ports.repositories import PositionRepository
from src.database.sqlserver import SqlServerClient
from src.domain.positions.entities import Position, PositionStatus

logger = logging.getLogger(__name__)


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _parse_json(raw: Optional[str], context: str = "") -> Optional[Dict[str, Any]]:
    if not raw or not raw.strip():
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("Invalid JSON in %s: %s", context or "position", e)
        return None


def _status_from_row(row: Any, position_id: str = "?") -> PositionStatus:
    s = getattr(row, "status", "detected") or "detected"
    try:
        return PositionStatus(s)
    except ValueError:
        logger.warning("Invalid position status %r for position_id=%s", s, position_id)
        return PositionStatus.DETECTED


def _row_to_position(row: Any) -> Position:
    pid = getattr(row, "id", "")
    created = _ensure_utc(getattr(row, "created_at", None))
    updated = _ensure_utc(getattr(row, "updated_at", None))
    if created is None or updated is None:
        raise ValueError("positions row missing required created_at/updated_at")
    return Position(
        id=pid,
        aisle_id=row.aisle_id or "",
        status=_status_from_row(row, pid),
        confidence=float(getattr(row, "confidence", 0)),
        needs_review=bool(getattr(row, "needs_review", False)),
        primary_evidence_id=getattr(row, "primary_evidence_id", None),
        created_at=created,
        updated_at=updated,
        detected_summary_json=_parse_json(getattr(row, "detected_summary_json", None), f"position id={pid}"),
        corrected_summary_json=_parse_json(getattr(row, "corrected_summary_json", None), f"position id={pid}"),
    )


class SqlPositionRepository(PositionRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def save(self, position: Position) -> None:
        if position.created_at is None or position.updated_at is None:
            raise ValueError("Position created_at and updated_at are required")
        created = _ensure_utc(position.created_at)
        updated = _ensure_utc(position.updated_at)
        det_json = json.dumps(position.detected_summary_json, ensure_ascii=False) if position.detected_summary_json else None
        corr_json = json.dumps(position.corrected_summary_json, ensure_ascii=False) if position.corrected_summary_json else None
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE positions
                SET aisle_id = ?, status = ?, confidence = ?, needs_review = ?,
                    primary_evidence_id = ?, updated_at = ?, detected_summary_json = ?, corrected_summary_json = ?
                WHERE id = ?
                """,
                (
                    position.aisle_id,
                    position.status.value,
                    position.confidence,
                    position.needs_review,
                    position.primary_evidence_id,
                    updated,
                    det_json,
                    corr_json,
                    position.id,
                ),
            )
            if cur.rowcount == 0:
                cur.execute(
                    """
                    INSERT INTO positions (id, aisle_id, status, confidence, needs_review, primary_evidence_id, created_at, updated_at, detected_summary_json, corrected_summary_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        position.id,
                        position.aisle_id,
                        position.status.value,
                        position.confidence,
                        position.needs_review,
                        position.primary_evidence_id,
                        created,
                        updated,
                        det_json,
                        corr_json,
                    ),
                )

    def get_by_id(self, position_id: str) -> Optional[Position]:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, aisle_id, status, confidence, needs_review, primary_evidence_id,
                       created_at, updated_at, detected_summary_json, corrected_summary_json
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
        status: Optional[str] = None,
        needs_review: Optional[bool] = None,
        min_confidence: Optional[float] = None,
        sku_filter: Optional[str] = None,
        page: int = 1,
        page_size: int = 25,
    ) -> Sequence[Position]:
        conditions = ["p.aisle_id = ?"]
        params: list = [aisle_id]
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
        if join_product_records:
            sql = f"""
                SELECT DISTINCT p.id, p.aisle_id, p.status, p.confidence, p.needs_review, p.primary_evidence_id,
                       p.created_at, p.updated_at, p.detected_summary_json, p.corrected_summary_json
                FROM positions p
                INNER JOIN product_records pr ON pr.position_id = p.id
                WHERE {where}
                ORDER BY p.created_at ASC, p.id ASC
                OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
                """
        else:
            sql = f"""
                SELECT p.id, p.aisle_id, p.status, p.confidence, p.needs_review, p.primary_evidence_id,
                       p.created_at, p.updated_at, p.detected_summary_json, p.corrected_summary_json
                FROM positions p
                WHERE {where}
                ORDER BY p.created_at ASC, p.id ASC
                OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
                """
        with self._client.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [_row_to_position(row) for row in rows]

    def list_by_aisle_query(
        self, aisle_id: str, query: Optional[PositionListQuery] = None
    ) -> Sequence[Position]:
        q = query or PositionListQuery()
        return self.list_by_aisle(
            aisle_id,
            status=q.status,
            needs_review=q.needs_review,
            min_confidence=q.min_confidence,
            sku_filter=q.sku_filter,
            page=q.page,
            page_size=q.page_size,
        )

    def list_by_aisles(self, aisle_ids: Sequence[str]) -> Sequence[Position]:
        if not aisle_ids:
            return []
        placeholders = ",".join("?" * len(aisle_ids))
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, aisle_id, status, confidence, needs_review, primary_evidence_id,
                       created_at, updated_at, detected_summary_json, corrected_summary_json
                FROM positions
                WHERE aisle_id IN ({placeholders})
                ORDER BY created_at ASC, id ASC
                """,
                list(aisle_ids),
            )
            rows = cur.fetchall()
        return [_row_to_position(row) for row in rows]
