"""Tests for MemoryReviewActionRepository — Épica 8."""

from __future__ import annotations

from datetime import datetime, timezone

from src.domain.reviews.entities import ReviewAction, ReviewActionType
from src.infrastructure.repositories.memory_review_action_repository import MemoryReviewActionRepository


def test_list_by_position_returns_ordered_by_created_at_then_id() -> None:
    """In-memory repo returns same explicit order as SQL: created_at ASC, id ASC."""
    repo = MemoryReviewActionRepository()
    t1 = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2025, 3, 6, 12, 1, 0, tzinfo=timezone.utc)
    pos_id = "pos-1"
    repo.save(
        ReviewAction(
            id="b-second",
            position_id=pos_id,
            action_type=ReviewActionType.CONFIRM,
            before_json={},
            after_json={},
            created_at=t2,
        )
    )
    repo.save(
        ReviewAction(
            id="a-first",
            position_id=pos_id,
            action_type=ReviewActionType.CONFIRM,
            before_json={},
            after_json={},
            created_at=t1,
        )
    )
    repo.save(
        ReviewAction(
            id="c-same-time",
            position_id=pos_id,
            action_type=ReviewActionType.CONFIRM,
            before_json={},
            after_json={},
            created_at=t1,
        )
    )
    result = repo.list_by_position(pos_id)
    assert [r.id for r in result] == ["a-first", "c-same-time", "b-second"]
