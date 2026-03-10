"""
GetPositionDetail use case — v3.0 Épica 6.

Returns a position with its product records and evidences.
Fails if inventory/aisle/position do not exist or do not match.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from src.application.ports.repositories import (
    AisleRepository,
    EvidenceRepository,
    InventoryRepository,
    PositionRepository,
    ProductRecordRepository,
    ReviewActionRepository,
)
from src.application.use_cases.review_validation import resolve_position
from src.domain.evidence.entities import Evidence
from src.domain.positions.entities import Position
from src.domain.products.entities import ProductRecord
from src.domain.reviews.entities import ReviewAction


@dataclass
class PositionDetailResult:
    position: Position
    products: Sequence[ProductRecord]
    evidences: Sequence[Evidence]
    review_actions: Sequence[ReviewAction]


class GetPositionDetailUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        position_repo: PositionRepository,
        product_record_repo: ProductRecordRepository,
        evidence_repo: EvidenceRepository,
        review_repo: ReviewActionRepository,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._position_repo = position_repo
        self._product_record_repo = product_record_repo
        self._evidence_repo = evidence_repo
        self._review_repo = review_repo

    def execute(
        self,
        inventory_id: str,
        aisle_id: str,
        position_id: str,
    ) -> PositionDetailResult:
        position = resolve_position(
            self._inventory_repo,
            self._aisle_repo,
            self._position_repo,
            inventory_id,
            aisle_id,
            position_id,
        )
        products = self._product_record_repo.list_by_position(position_id)
        evidences = self._evidence_repo.list_by_entity("position", position_id)
        review_actions = self._review_repo.list_by_position(position_id)
        return PositionDetailResult(
            position=position,
            products=products,
            evidences=evidences,
            review_actions=review_actions,
        )
