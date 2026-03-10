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
)
from src.application.errors import AisleNotFoundError, InventoryNotFoundError, PositionNotFoundError
from src.domain.evidence.entities import Evidence
from src.domain.positions.entities import Position
from src.domain.products.entities import ProductRecord


@dataclass
class PositionDetailResult:
    position: Position
    products: Sequence[ProductRecord]
    evidences: Sequence[Evidence]


class GetPositionDetailUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        position_repo: PositionRepository,
        product_record_repo: ProductRecordRepository,
        evidence_repo: EvidenceRepository,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._position_repo = position_repo
        self._product_record_repo = product_record_repo
        self._evidence_repo = evidence_repo

    def execute(
        self,
        inventory_id: str,
        aisle_id: str,
        position_id: str,
    ) -> PositionDetailResult:
        inv = self._inventory_repo.get_by_id(inventory_id)
        if inv is None:
            raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")
        aisle = self._aisle_repo.get_by_id(aisle_id)
        if aisle is None:
            raise AisleNotFoundError(f"Aisle not found: {aisle_id}")
        if aisle.inventory_id != inventory_id:
            raise AisleNotFoundError(
                f"Aisle {aisle_id} does not belong to inventory {inventory_id}"
            )
        position = self._position_repo.get_by_id(position_id)
        if position is None:
            raise PositionNotFoundError(f"Position not found: {position_id}")
        if position.aisle_id != aisle_id:
            raise PositionNotFoundError(
                f"Position {position_id} does not belong to aisle {aisle_id}"
            )
        products = self._product_record_repo.list_by_position(position_id)
        evidences = self._evidence_repo.list_by_entity("position", position_id)
        return PositionDetailResult(
            position=position,
            products=products,
            evidences=evidences,
        )
