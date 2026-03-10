"""
UpdateProductSku use case — v3.0 Épica 8 (HU-8.3).

Corrects SKU and/or description for a product; sets position to corrected and records ReviewAction.
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


class UpdateProductSkuUseCase:
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
        sku: str,
        description: str | None = None,
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
        sku = (sku or "").strip()
        if not sku:
            raise ValueError("sku is required")

        now = self._clock.now()
        before_sku = product.sku
        before_description = product.description
        product.sku = sku
        if description is not None:
            product.description = description.strip() or None
        product.updated_at = now
        self._product_record_repo.save(product)

        position.status = PositionStatus.CORRECTED
        position.updated_at = now
        self._position_repo.save(position)

        review = ReviewAction(
            id=str(uuid.uuid4()),
            position_id=position_id,
            action_type=ReviewActionType.UPDATE_SKU,
            before_json={"product_id": product_id, "sku": before_sku, "description": before_description},
            after_json={
                "product_id": product_id,
                "sku": product.sku,
                "description": product.description,
            },
            created_at=now,
        )
        self._review_repo.save(review)
