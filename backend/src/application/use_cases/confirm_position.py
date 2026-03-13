"""
ConfirmPosition use case — v3.0 Épica 8 (HU-8.1).

Confirms a detected position without changes; sets status to reviewed and records a ReviewAction.
"""

from __future__ import annotations

import uuid

from src.application.ports.clock import Clock
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    PositionRepository,
    ReviewActionRepository,
)
from src.application.use_cases.review_validation import resolve_position, ensure_position_not_deleted
from src.domain.positions.entities import PositionStatus
from src.domain.reviews.entities import ReviewAction, ReviewActionType


class ConfirmPositionUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        position_repo: PositionRepository,
        review_repo: ReviewActionRepository,
        clock: Clock,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._position_repo = position_repo
        self._review_repo = review_repo
        self._clock = clock

    def execute(
        self,
        inventory_id: str,
        aisle_id: str,
        position_id: str,
    ) -> None:
        position = resolve_position(
            self._inventory_repo,
            self._aisle_repo,
            self._position_repo,
            inventory_id,
            aisle_id,
            position_id,
        )
        ensure_position_not_deleted(position)
        now = self._clock.now()
        before_status = position.status.value
        position.status = PositionStatus.REVIEWED
        position.updated_at = now
        self._position_repo.save(position)

        review = ReviewAction(
            id=str(uuid.uuid4()),
            position_id=position_id,
            action_type=ReviewActionType.CONFIRM,
            before_json={"status": before_status},
            after_json={"status": PositionStatus.REVIEWED.value},
            created_at=now,
        )
        self._review_repo.save(review)
