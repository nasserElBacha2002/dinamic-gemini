"""
MarkPositionUnknown use case.

Persists an explicit terminal operator resolution that the position outcome is unknown.
This is distinct from:
- quantity provenance such as ``qty_source="unknown"``
- product-identification issues such as a primary product row with ``sku="UNKNOWN"``
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
from src.application.services.aisle_review_lifecycle_sync import AisleReviewLifecycleSync
from src.application.use_cases.review_validation import (
    load_aisle_and_ensure_review_mutable,
    resolve_position,
    ensure_position_not_deleted,
)
from src.domain.positions.entities import PositionReviewResolution, PositionStatus
from src.domain.reviews.entities import ReviewAction, ReviewActionType


class MarkPositionUnknownUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        position_repo: PositionRepository,
        review_repo: ReviewActionRepository,
        clock: Clock,
        aisle_review_sync: AisleReviewLifecycleSync,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._position_repo = position_repo
        self._review_repo = review_repo
        self._clock = clock
        self._aisle_review_sync = aisle_review_sync

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
        load_aisle_and_ensure_review_mutable(self._aisle_repo, aisle_id, position)
        now = self._clock.now()
        before_status = position.status.value
        before_resolution = (
            position.review_resolution.value
            if position.review_resolution is not None
            else None
        )

        position.status = PositionStatus.REVIEWED
        position.review_resolution = PositionReviewResolution.UNKNOWN
        position.needs_review = False
        position.updated_at = now
        self._position_repo.save(position)

        review = ReviewAction(
            id=str(uuid.uuid4()),
            position_id=position_id,
            action_type=ReviewActionType.MARK_UNKNOWN,
            before_json={
                "status": before_status,
                "review_resolution": before_resolution,
            },
            after_json={
                "status": PositionStatus.REVIEWED.value,
                "review_resolution": PositionReviewResolution.UNKNOWN.value,
            },
            created_at=now,
        )
        self._review_repo.save(review)
        self._aisle_review_sync.after_review_mutation(inventory_id, aisle_id)
