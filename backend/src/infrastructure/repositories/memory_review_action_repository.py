"""
In-memory implementation of ReviewActionRepository — v3.0 Épica 8.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.application.ports.repositories import ReviewActionRepository
from src.domain.reviews.entities import ReviewAction


class MemoryReviewActionRepository(ReviewActionRepository):
    def __init__(self) -> None:
        self._store: list[ReviewAction] = []

    def save(self, review: ReviewAction) -> None:
        self._store.append(review)

    def list_by_position(self, position_id: str) -> Sequence[ReviewAction]:
        matching = [r for r in self._store if r.position_id == position_id]
        return sorted(matching, key=lambda r: (r.created_at, r.id))
