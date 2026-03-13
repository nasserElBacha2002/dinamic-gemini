"""
SQL Server implementation of ReviewActionRepository — v3.0 Épica 8.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence

from src.application.ports.repositories import ReviewActionRepository
from src.database.sqlserver import SqlServerClient
from src.domain.reviews.entities import ReviewAction, ReviewActionType

logger = logging.getLogger(__name__)


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _parse_json_field(
    raw: Any,
    field_name: str,
    review_id: str,
    position_id: str,
) -> Dict[str, Any]:
    """Parse JSON field from row; log warning on invalid JSON, return {} as safe fallback."""
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError as e:
            logger.warning(
                "Invalid JSON in review_actions.%s for id=%s position_id=%s: %s",
                field_name,
                review_id,
                position_id,
                e,
            )
            return {}
    return {}


def _row_to_review(row: Any) -> ReviewAction:
    action_type_raw = getattr(row, "action_type", "confirm") or "confirm"
    try:
        action_type = ReviewActionType(action_type_raw)
    except ValueError:
        action_type = ReviewActionType.CONFIRM
    created = _ensure_utc(getattr(row, "created_at", None))
    if created is None:
        raise ValueError("review_actions row missing created_at")
    before_raw = getattr(row, "before_json", None)
    after_raw = getattr(row, "after_json", None)
    before = _parse_json_field(before_raw, "before_json", getattr(row, "id", ""), getattr(row, "position_id", ""))
    after = _parse_json_field(after_raw, "after_json", getattr(row, "id", ""), getattr(row, "position_id", ""))
    return ReviewAction(
        id=getattr(row, "id", ""),
        position_id=row.position_id or "",
        action_type=action_type,
        before_json=before,
        after_json=after,
        created_at=created,
        user_id=getattr(row, "user_id", None) or None,
        comment=getattr(row, "comment", None) or None,
    )


class SqlReviewActionRepository(ReviewActionRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def save(self, review: ReviewAction) -> None:
        if review.created_at is None:
            raise ValueError("ReviewAction created_at is required")
        created = _ensure_utc(review.created_at)
        before_str = json.dumps(review.before_json, ensure_ascii=False)
        after_str = json.dumps(review.after_json, ensure_ascii=False)
        with self._client.cursor() as cur:
            cur.execute(
                """
                INSERT INTO review_actions (id, position_id, action_type, before_json, after_json, created_at, user_id, comment)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review.id,
                    review.position_id,
                    review.action_type.value,
                    before_str,
                    after_str,
                    created,
                    review.user_id,
                    review.comment,
                ),
            )

    def list_by_position(self, position_id: str) -> Sequence[ReviewAction]:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, position_id, action_type, before_json, after_json, created_at, user_id, comment
                FROM review_actions
                WHERE position_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (position_id,),
            )
            rows = cur.fetchall()
        return [_row_to_review(row) for row in rows]
