"""
PersistAisleResult use case — v3.0 Épica 6, v3.2.3 consolidation.

Maps a hybrid pipeline report to v3 domain entities and persists them.
v3.2.3: Also persists raw_labels and runs RecomputeConsolidatedCountsUseCase so
final quantity comes from normalized/final_count layer.

Atomicity: Saves positions, then product_records, then evidences, then raw_labels;
then recomputes consolidated counts (normalized + final) and updates product records.
On any save failure we re-raise so the caller can mark the job/aisle as failed.

Phase 2: This use case does **not** set ``aisles.operational_job_id`` (promotion workflow).
Default reads without ``job_id`` use ``ResultContextResolver`` — **operational_job_id**
if set, else **legacy** null-job rows only (no implicit latest-job slice).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.application.ports.repositories import (
    AisleRepository,
    EvidenceRepository,
    PositionRepository,
    ProductRecordRepository,
    RawLabelRepository,
)
from src.application.ports.clock import Clock
from src.application.use_cases.recompute_consolidated_counts import (
    RecomputeConsolidatedCountsCommand,
    RecomputeConsolidatedCountsUseCase,
)
from src.infrastructure.pipeline.v3_report_mapper import map_hybrid_report_to_domain

logger = logging.getLogger(__name__)


@dataclass
class PersistAisleResultCommand:
    aisle_id: str
    job_id: str
    report: dict
    run_dir: Path
    run_id: str = "run"


class PersistAisleResultUseCase:
    def __init__(
        self,
        position_repo: PositionRepository,
        product_record_repo: ProductRecordRepository,
        evidence_repo: EvidenceRepository,
        clock: Clock,
        aisle_repo: Optional[AisleRepository] = None,
        raw_label_repo: Optional[RawLabelRepository] = None,
        recompute_consolidated_uc: Optional[RecomputeConsolidatedCountsUseCase] = None,
    ) -> None:
        self._position_repo = position_repo
        self._product_record_repo = product_record_repo
        self._evidence_repo = evidence_repo
        self._clock = clock
        self._aisle_repo = aisle_repo
        self._raw_label_repo = raw_label_repo
        self._recompute_uc = recompute_consolidated_uc

    def execute(self, command: PersistAisleResultCommand) -> None:
        now = self._clock.now()
        if self._aisle_repo is None:
            raise ValueError("PersistAisleResultUseCase requires AisleRepository for v3.2.3 consolidation")
        aisle = self._aisle_repo.get_by_id(command.aisle_id)
        if aisle is None:
            raise ValueError(f"Aisle not found while persisting results: {command.aisle_id}")
        inventory_id = aisle.inventory_id

        mapped = map_hybrid_report_to_domain(
            aisle_id=command.aisle_id,
            report=command.report,
            run_dir=command.run_dir,
            run_id=command.run_id,
            job_id=command.job_id,
            now=now,
            inventory_id=inventory_id,
        )
        try:
            for position in mapped.positions:
                self._position_repo.save(position)
            logger.debug("PersistAisleResult: saved %d positions for aisle %s", len(mapped.positions), command.aisle_id)
            for product in mapped.product_records:
                self._product_record_repo.save(product)
            logger.debug("PersistAisleResult: saved %d product_records for aisle %s", len(mapped.product_records), command.aisle_id)
            for evidence in mapped.evidences:
                self._evidence_repo.save(evidence)
            logger.debug("PersistAisleResult: saved %d evidences for aisle %s", len(mapped.evidences), command.aisle_id)

            if self._raw_label_repo and mapped.raw_labels:
                self._raw_label_repo.save_many(mapped.raw_labels)
                logger.debug("PersistAisleResult: saved %d raw_labels for aisle %s", len(mapped.raw_labels), command.aisle_id)

            if self._recompute_uc and inventory_id and self._raw_label_repo:
                result = self._recompute_uc.execute(
                    RecomputeConsolidatedCountsCommand(
                        inventory_id=inventory_id,
                        aisle_id=command.aisle_id,
                        # Hotfix v3.2.5: merge/consolidation is non-authoritative in main flow.
                        # Keep explicit quantity resolved by pipeline mapping; do not overwrite ProductRecord.
                        apply_to_product_records=False,
                        job_scope=command.job_id,
                    )
                )
                logger.debug(
                    "PersistAisleResult: recompute consolidated raw=%d normalized=%d final=%d product_updated=%d",
                    result.raw_count,
                    result.normalized_count,
                    result.final_count,
                    result.product_records_updated,
                )
        except Exception as e:
            logger.exception("PersistAisleResult failed for aisle %s job %s: %s", command.aisle_id, command.job_id, e)
            raise
