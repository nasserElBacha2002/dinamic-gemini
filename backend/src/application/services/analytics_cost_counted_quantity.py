"""Counted quantity for analytics cost-summary (UI/export-aligned operational grain).

Cost aggregates are job-grain (``finished_at`` window). Counted quantity uses the same rules as
business exports and Aisle Results UI: ``ExportQuantityRollupService`` with
``exclude_traceability_invalid_from_totals=False`` (only deleted positions excluded).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass

from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    PositionRepository,
    ProductRecordRepository,
)
from src.application.services.aisle_results_export_source import ui_aligned_rollup_service
from src.application.services.export_inventory_collector import ExportInventoryCollector
from src.application.services.export_quantity_rollup import ExportQuantityRollupService
from src.application.services.export_summary_builder import ExportSummaryBuilder
from src.application.services.result_context_resolver import ResultContextResolver
from src.domain.aisle.entities import Aisle

logger = logging.getLogger(__name__)

COUNTED_QUANTITY_MAX_AISLES = 200


@dataclass(frozen=True)
class CountedQuantityScope:
    total_counted_quantity: int | None
    by_inventory_id: dict[str, int]
    by_aisle_id: dict[str, int]
    warnings: tuple[str, ...]


def resolve_aisle_ids_for_quantity(
    *,
    inventory_id: str | None,
    aisle_id: str | None,
    aisle_repo: AisleRepository,
    job_aisle_ids: set[str],
) -> set[str]:
    if aisle_id:
        return {aisle_id}
    if inventory_id:
        return {a.id for a in aisle_repo.list_by_inventory(inventory_id)}
    return set(job_aisle_ids)


class AnalyticsCostCountedQuantityService:
    def __init__(
        self,
        *,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        position_repo: PositionRepository,
        product_record_repo: ProductRecordRepository,
        result_context_resolver: ResultContextResolver | None = None,
        rollup_service: ExportQuantityRollupService | None = None,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        rollup = rollup_service or ui_aligned_rollup_service()
        self._rollup_builder = ExportSummaryBuilder(rollup_service=rollup)
        self._collector = ExportInventoryCollector(
            inventory_repo=inventory_repo,
            aisle_repo=aisle_repo,
            position_repo=position_repo,
            product_record_repo=product_record_repo,
            result_context_resolver=result_context_resolver or ResultContextResolver(),
            rollup_service=rollup,
        )

    def compute(
        self,
        *,
        inventory_id: str | None,
        aisle_id: str | None,
        job_aisle_ids: set[str],
    ) -> CountedQuantityScope:
        aisle_ids = resolve_aisle_ids_for_quantity(
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            aisle_repo=self._aisle_repo,
            job_aisle_ids=job_aisle_ids,
        )
        warnings: list[str] = []
        if not aisle_ids:
            warnings.append("COUNTED_QUANTITY_NOT_AVAILABLE")
            return CountedQuantityScope(
                total_counted_quantity=None,
                by_inventory_id={},
                by_aisle_id={},
                warnings=tuple(warnings),
            )
        if len(aisle_ids) > COUNTED_QUANTITY_MAX_AISLES:
            warnings.append("COUNTED_QUANTITY_SCOPE_CAPPED")
            aisle_ids = set(sorted(aisle_ids)[:COUNTED_QUANTITY_MAX_AISLES])

        by_inventory: dict[str, int] = defaultdict(int)
        by_aisle: dict[str, int] = defaultdict(int)
        total = 0

        aisles_by_inventory: dict[str, list[Aisle]] = defaultdict(list)
        for aid in aisle_ids:
            aisle = self._aisle_repo.get_by_id(aid)
            if aisle is None:
                continue
            aisles_by_inventory[aisle.inventory_id].append(aisle)

        for inv_id, inv_aisles in aisles_by_inventory.items():
            try:
                if len(inv_aisles) == 1 and inventory_id and aisle_id:
                    data = self._collector.collect_aisle(inv_id, inv_aisles[0].id)
                else:
                    data = self._collector.collect_inventory(inv_id)
            except Exception:
                logger.exception("counted_quantity_collect_failed inventory_id=%s", inv_id)
                warnings.append("COUNTED_QUANTITY_NOT_AVAILABLE")
                continue

            rollups = self._rollup_builder.build_rollups(data)
            for at in rollups.aisle_totals:
                if at.aisle_id not in aisle_ids:
                    continue
                by_aisle[at.aisle_id] = at.total_counted_quantity
                by_inventory[inv_id] += at.total_counted_quantity
                total += at.total_counted_quantity

        if not by_aisle and "COUNTED_QUANTITY_NOT_AVAILABLE" not in warnings:
            warnings.append("COUNTED_QUANTITY_NOT_AVAILABLE")
            return CountedQuantityScope(
                total_counted_quantity=None,
                by_inventory_id={},
                by_aisle_id={},
                warnings=tuple(warnings),
            )

        return CountedQuantityScope(
            total_counted_quantity=total,
            by_inventory_id=dict(by_inventory),
            by_aisle_id=dict(by_aisle),
            warnings=tuple(warnings),
        )
