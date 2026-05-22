"""
DeletePosition use case — v3.0 Épica 8 (HU-8.4).

Logically deletes a position (status -> deleted); does not remove records; records ReviewAction.
"""

from __future__ import annotations

import uuid

from src.application.errors import PositionDeletedError
from src.application.ports.clock import Clock
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    PositionRepository,
    ReviewActionRepository,
)
from src.application.services.aisle_review_lifecycle_sync import AisleReviewLifecycleSync
from src.application.use_cases.shared.review_validation import (
    ensure_review_job_matches_position,
    resolve_position,
    storage_job_id_for_review_audit,
)
from src.domain.positions.entities import PositionReviewResolution, PositionStatus
from src.domain.reviews.entities import ReviewAction, ReviewActionType


class DeletePositionUseCase:
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
        job_id: str | None,
    ) -> None:
        position = resolve_position(
            self._inventory_repo,
            self._aisle_repo,
            self._position_repo,
            inventory_id,
            aisle_id,
            position_id,
        )
        if position.status == PositionStatus.DELETED:
            raise PositionDeletedError(f"Position {position_id} is already deleted")
        ensure_review_job_matches_position(job_id, position)
        now = self._clock.now()
        before_status = position.status.value
        before_resolution = (
            position.review_resolution.value if position.review_resolution is not None else None
        )
        position.status = PositionStatus.DELETED
        position.review_resolution = PositionReviewResolution.DELETED
        position.needs_review = False
        position.updated_at = now
        self._position_repo.save(position)

        review = ReviewAction(
            id=str(uuid.uuid4()),
            position_id=position_id,
            action_type=ReviewActionType.DELETE_POSITION,
            before_json={
                "status": before_status,
                "review_resolution": before_resolution,
            },
            after_json={
                "status": PositionStatus.DELETED.value,
                "review_resolution": PositionReviewResolution.DELETED.value,
            },
            created_at=now,
            job_id=storage_job_id_for_review_audit(position),
        )
        self._review_repo.save(review)
        self._aisle_review_sync.after_review_mutation(inventory_id, aisle_id)
