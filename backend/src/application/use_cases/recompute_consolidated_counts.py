"""
RecomputeConsolidatedCountsUseCase — v3.2.3.

Orchestrates: read raw labels for scope → normalize → persist normalized →
build final_count → persist final_count. Optionally applies final quantity to ProductRecords.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.application.ports.repositories import (
    FinalCountRepository,
    NormalizedLabelRepository,
    PositionRepository,
    ProductRecordRepository,
    RawLabelRepository,
)
from src.application.services.final_count_builder import FinalCountBuilder
from src.application.services.label_normalization import LabelNormalizationService
from src.domain.labels.merge import MergeRuleEngine

logger = logging.getLogger(__name__)


@dataclass
class RecomputeConsolidatedCountsCommand:
    inventory_id: str
    aisle_id: str
    apply_to_product_records: bool = True


@dataclass
class RecomputeConsolidatedCountsResult:
    raw_count: int
    normalized_count: int
    final_count: int
    product_records_updated: int


class RecomputeConsolidatedCountsUseCase:
    """
    Run full flow: raw → normalized → final_count.
    If apply_to_product_records, update ProductRecord.detected_quantity from final_count.
    """

    def __init__(
        self,
        raw_label_repo: RawLabelRepository,
        normalized_label_repo: NormalizedLabelRepository,
        final_count_repo: FinalCountRepository,
        product_record_repo: ProductRecordRepository,
        position_repo: PositionRepository,
        normalization_service: LabelNormalizationService,
        final_count_builder: FinalCountBuilder,
    ) -> None:
        self._raw_repo = raw_label_repo
        self._normalized_repo = normalized_label_repo
        self._final_repo = final_count_repo
        self._product_repo = product_record_repo
        self._position_repo = position_repo
        self._normalization = normalization_service
        self._builder = final_count_builder

    def execute(self, command: RecomputeConsolidatedCountsCommand) -> RecomputeConsolidatedCountsResult:
        inv_id = command.inventory_id
        aisle_id = command.aisle_id

        raw_labels = list(self._raw_repo.list_for_scope(inv_id, aisle_id))
        if not raw_labels:
            logger.debug("RecomputeConsolidatedCounts: no raw labels for scope %s/%s", inv_id, aisle_id)
            self._normalized_repo.replace_for_scope(inv_id, aisle_id)
            self._final_repo.replace_for_scope(inv_id, aisle_id)
            return RecomputeConsolidatedCountsResult(
                raw_count=0,
                normalized_count=0,
                final_count=0,
                product_records_updated=0,
            )

        normalized = self._normalization.normalize(raw_labels)
        self._normalized_repo.replace_for_scope(inv_id, aisle_id)
        self._normalized_repo.save_many(normalized)

        final_records = self._builder.build(normalized)
        self._final_repo.replace_for_scope(inv_id, aisle_id)
        self._final_repo.save_many(final_records)

        product_updated = 0
        if command.apply_to_product_records:
            product_updated = self._apply_final_count_to_product_records(inv_id, aisle_id, final_records)

        return RecomputeConsolidatedCountsResult(
            raw_count=len(raw_labels),
            normalized_count=len(normalized),
            final_count=len(final_records),
            product_records_updated=product_updated,
        )

    def _apply_final_count_to_product_records(
        self,
        inventory_id: str,
        aisle_id: str,
        final_records: list,
    ) -> int:
        """
        Project final_count into ProductRecord.detected_quantity for the whole scope.

        For each position in the aisle:
        - If there is a FinalCountRecord for (position_id, sku), set detected_quantity to that quantity.
        - If there is no FinalCountRecord for (position_id, sku), set detected_quantity to 0.

        This avoids stale quantities from pre-consolidation mapping.
        """
        # Build lookup from (position_id, sku) -> quantity from final_count.
        qty_by_pos_sku: dict[tuple[str, str], int] = {}
        for rec in final_records:
            if not rec.position_id:
                continue
            key = (rec.position_id, (rec.sku or ""))
            qty_by_pos_sku[key] = rec.quantity

        updated = 0
        # Enumerate all positions in aisle and reset product_records to consolidated quantities.
        positions = self._position_repo.list_by_aisle(aisle_id)
        for pos in positions:
            products = list(self._product_repo.list_by_position(pos.id))
            for prod in products:
                key = (prod.position_id, prod.sku or "")
                new_qty = qty_by_pos_sku.get(key, 0)
                if prod.detected_quantity != new_qty:
                    prod.detected_quantity = new_qty
                    # Mark as consolidated source for audit.
                    prod.qty_source = "consolidated"
                    self._product_repo.save(prod)
                    updated += 1
        return updated
