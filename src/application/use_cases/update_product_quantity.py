"""
UpdateProductQuantity use case — v3.0 Épica 8 (HU-8.2).

Corrects the quantity for a product; keeps detected_quantity; sets position to corrected and records ReviewAction.
"""

from __future__ import annotations

import uuid

from src.application.ports.clock import Clock
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    PositionRepository,
    ProductRecordRepository,
    ReviewActionRepository,
)
from src.application.use_cases.review_validation import resolve_position, resolve_product_for_position, ensure_position_not_deleted
from src.domain.positions.entities import PositionStatus
from src.domain.reviews.entities import ReviewAction, ReviewActionType


class UpdateProductQuantityUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        position_repo: PositionRepository,
        product_record_repo: ProductRecordRepository,
        review_repo: ReviewActionRepository,
        clock: Clock,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._position_repo = position_repo
        self._product_record_repo = product_record_repo
        self._review_repo = review_repo
        self._clock = clock

    def execute(
        self,
        inventory_id: str,
        aisle_id: str,
        position_id: str,
        product_id: str,
        corrected_quantity: int,
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
        product = resolve_product_for_position(
            self._product_record_repo,
            position_id,
            product_id,
        )
        if corrected_quantity < 0:
            raise ValueError("corrected_quantity must be non-negative")

        now = self._clock.now()
        before_quantity = product.corrected_quantity
        product.corrected_quantity = corrected_quantity
        product.updated_at = now
        self._product_record_repo.save(product)

        position.status = PositionStatus.CORRECTED
        position.updated_at = now
        self._position_repo.save(position)

        review = ReviewAction(
            id=str(uuid.uuid4()),
            position_id=position_id,
            action_type=ReviewActionType.UPDATE_QUANTITY,
            before_json={"product_id": product_id, "corrected_quantity": before_quantity},
            after_json={"product_id": product_id, "corrected_quantity": corrected_quantity},
            created_at=now,
        )
        self._review_repo.save(review)
