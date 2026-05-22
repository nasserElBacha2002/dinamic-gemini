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
from src.application.services.aisle_review_lifecycle_sync import AisleReviewLifecycleSync
from src.application.use_cases.shared.review_validation import (
    ensure_position_not_deleted,
    ensure_review_job_matches_position,
    resolve_position,
    resolve_product_for_position,
    resolve_single_product_for_position,
    storage_job_id_for_review_audit,
)
from src.domain.positions.entities import PositionReviewResolution, PositionStatus
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
        aisle_review_sync: AisleReviewLifecycleSync,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._position_repo = position_repo
        self._product_record_repo = product_record_repo
        self._review_repo = review_repo
        self._clock = clock
        self._aisle_review_sync = aisle_review_sync

    def execute(
        self,
        inventory_id: str,
        aisle_id: str,
        position_id: str,
        job_id: str | None,
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
        ensure_review_job_matches_position(job_id, position)
        pid = (product_id or "").strip()
        if pid:
            product = resolve_product_for_position(
                self._product_record_repo,
                position_id,
                pid,
            )
        else:
            product = resolve_single_product_for_position(
                self._product_record_repo,
                position_id,
            )
            pid = product.id
        sku = (sku or "").strip()
        if not sku:
            raise ValueError("sku is required")

        now = self._clock.now()
        before_sku = product.sku
        before_description = product.description
        before_resolution = (
            position.review_resolution.value if position.review_resolution is not None else None
        )
        product.sku = sku
        if description is not None:
            clean_description = description.strip()
            product.description = clean_description or None
        product.updated_at = now
        self._product_record_repo.save(product)

        position.status = PositionStatus.CORRECTED
        position.review_resolution = PositionReviewResolution.SKU_CORRECTED
        position.needs_review = False
        position.updated_at = now
        # Transitional compatibility: keep legacy snapshot identity coherent on reread while
        # public consumers migrate to canonical product fields.
        if position.detected_summary_json is None:
            position.detected_summary_json = {"internal_code": sku}
        else:
            summary = dict(position.detected_summary_json)
            summary["internal_code"] = sku
            position.detected_summary_json = summary
        self._position_repo.save(position)

        review = ReviewAction(
            id=str(uuid.uuid4()),
            position_id=position_id,
            action_type=ReviewActionType.UPDATE_SKU,
            before_json={
                "product_id": pid,
                "sku": before_sku,
                "description": before_description,
                "review_resolution": before_resolution,
            },
            after_json={
                "product_id": pid,
                "sku": product.sku,
                "description": product.description,
                "review_resolution": PositionReviewResolution.SKU_CORRECTED.value,
            },
            created_at=now,
            job_id=storage_job_id_for_review_audit(position),
        )
        self._review_repo.save(review)
        self._aisle_review_sync.after_review_mutation(inventory_id, aisle_id)
