"""
GetPositionDetail use case — v3.0 Épica 6.

Returns a position with its product records and evidences.
Fails if inventory/aisle/position do not exist or do not match.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from src.application.ports.contracts import PositionListQuery
from src.application.ports.repositories import (
    AisleRepository,
    EvidenceRepository,
    InventoryRepository,
    PositionRepository,
    ProductRecordRepository,
    ReviewActionRepository,
)
from src.application.services.position_sku_consolidation import consolidate_positions_by_sku
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
        *,
        positions_aisle_raw_cap: int,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._position_repo = position_repo
        self._product_record_repo = product_record_repo
        self._evidence_repo = evidence_repo
        self._review_repo = review_repo
        self._raw_cap = max(1, int(positions_aisle_raw_cap))

    @staticmethod
    def _is_group_member(position: Position, requested_position_id: str) -> bool:
        summary = position.detected_summary_json if isinstance(position.detected_summary_json, dict) else {}
        aggregated = summary.get("aggregated_from_ids")
        if not isinstance(aggregated, list):
            return False
        return requested_position_id in aggregated

    def _resolve_operator_facing_position(self, position: Position) -> Position:
        raw_positions = list(
            self._position_repo.list_by_aisle_query(
                position.aisle_id,
                PositionListQuery(page=1, page_size=self._raw_cap, sort_by="created_at", sort_dir="asc"),
            )
        )
        consolidated = consolidate_positions_by_sku(raw_positions)
        for candidate in consolidated:
            if candidate.id == position.id or self._is_group_member(candidate, position.id):
                return candidate
        return position

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
        operator_position = self._resolve_operator_facing_position(position)
        products = self._product_record_repo.list_by_position(operator_position.id)
        evidences = self._evidence_repo.list_by_entity("position", operator_position.id)
        review_actions = self._review_repo.list_by_position(operator_position.id)
        return PositionDetailResult(
            position=operator_position,
            products=products,
            evidences=evidences,
            review_actions=review_actions,
        )
