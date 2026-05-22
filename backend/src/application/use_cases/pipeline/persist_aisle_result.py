"""
PersistAisleResult use case — v3.0 Épica 6, v3.2.3 consolidation.

Maps a hybrid pipeline report to v3 domain entities and persists them.
v3.2.3: Also persists raw_labels and runs RecomputeConsolidatedCountsUseCase so
final quantity comes from normalized/final_count layer.

Atomicity: Saves positions, then product_records, then evidences, then raw_labels;
then recomputes consolidated counts (normalized + final) and updates product records.
On any save failure we re-raise so the caller can mark the job/aisle as failed.

Phase 2: This use case does **not** set ``aisles.operational_job_id`` (promotion workflow for test).
For **production** inventories, ``V3JobExecutor._mark_success`` sets ``operational_job_id`` to the
succeeded ``process_aisle`` job so review mutations align with the operational slice.
Default reads without ``job_id`` use ``ResultContextResolver`` — **operational_job_id**
if set, else **legacy** null-job rows only (no implicit latest-job slice).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.application.dto.mapped_aisle_result import MappedAisleResult
from src.application.ports.clock import Clock
from src.application.ports.hybrid_report_to_domain_mapper import HybridReportToDomainMapper
from src.application.ports.repositories import (
    AisleRepository,
    EvidenceRepository,
    PositionRepository,
    ProductRecordRepository,
    RawLabelRepository,
)
from src.application.use_cases.pipeline.recompute_consolidated_counts import (
    RecomputeConsolidatedCountsCommand,
    RecomputeConsolidatedCountsUseCase,
)

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
        hybrid_mapper: HybridReportToDomainMapper,
        aisle_repo: AisleRepository | None = None,
        raw_label_repo: RawLabelRepository | None = None,
        recompute_consolidated_uc: RecomputeConsolidatedCountsUseCase | None = None,
    ) -> None:
        self._position_repo = position_repo
        self._product_record_repo = product_record_repo
        self._evidence_repo = evidence_repo
        self._clock = clock
        self._hybrid_mapper = hybrid_mapper
        self._aisle_repo = aisle_repo
        self._raw_label_repo = raw_label_repo
        self._recompute_uc = recompute_consolidated_uc

    def execute(self, command: PersistAisleResultCommand) -> None:
        now = self._clock.now()
        inventory_id = self._inventory_id_for_aisle(command.aisle_id)
        mapped = self._map_hybrid(command, inventory_id, now)
        self._raise_if_mapped_lengths_mismatch(command, mapped)
        self._persist_all(command, mapped, inventory_id)

    def _inventory_id_for_aisle(self, aisle_id: str) -> str:
        if self._aisle_repo is None:
            raise ValueError(
                "PersistAisleResultUseCase requires AisleRepository for v3.2.3 consolidation"
            )
        aisle = self._aisle_repo.get_by_id(aisle_id)
        if aisle is None:
            raise ValueError(f"Aisle not found while persisting results: {aisle_id}")
        return aisle.inventory_id

    def _map_hybrid(
        self, command: PersistAisleResultCommand, inventory_id: str, now: datetime
    ) -> MappedAisleResult:
        return self._hybrid_mapper(
            aisle_id=command.aisle_id,
            report=command.report,
            run_dir=command.run_dir,
            run_id=command.run_id,
            job_id=command.job_id,
            now=now,
            inventory_id=inventory_id,
        )

    def _raise_if_mapped_lengths_mismatch(
        self, command: PersistAisleResultCommand, mapped: MappedAisleResult
    ) -> None:
        report_entities = len(command.report.get("entities") or [])
        n_pos = len(mapped.positions)
        n_prod = len(mapped.product_records)
        n_evid = len(mapped.evidences)
        if n_pos != n_prod or n_prod != n_evid:
            logger.error(
                "v3.persist_aisle_result mapped_length_mismatch aisle_id=%s job_id=%s "
                "positions=%d product_records=%d evidences=%d raw_labels=%d",
                command.aisle_id,
                command.job_id,
                n_pos,
                n_prod,
                n_evid,
                len(mapped.raw_labels),
            )
            raise ValueError(
                f"PersistAisleResult invariant broken: positions={n_pos} product_records={n_prod} "
                f"evidences={n_evid} (must be equal before zip)"
            )
        logger.debug(
            "v3.persist_aisle_result mapped_counts aisle_id=%s job_id=%s report_entities=%d "
            "mapped_positions=%d",
            command.aisle_id,
            command.job_id,
            report_entities,
            n_pos,
        )

    def _persist_all(
        self,
        command: PersistAisleResultCommand,
        mapped: MappedAisleResult,
        inventory_id: str,
    ) -> None:
        try:
            persisted_positions = 0
            persisted_products = 0
            persisted_evidences = 0
            skipped_unknown_zero = 0
            for position, product, evidence in zip(
                mapped.positions, mapped.product_records, mapped.evidences
            ):
                final_quantity = product.detected_quantity
                if not should_persist_detected_position(product.sku, final_quantity):
                    skipped_unknown_zero += 1
                    logger.info(
                        "PersistAisleResult: skipped position persistence sku=%r final_qty=%s reason=%s",
                        product.sku,
                        final_quantity,
                        "unknown_sku_with_zero_qty",
                    )
                    continue
                self._position_repo.save(position)
                self._product_record_repo.save(product)
                self._evidence_repo.save(evidence)
                persisted_positions += 1
                persisted_products += 1
                persisted_evidences += 1
            logger.info(
                "v3.persist_aisle_result summary aisle_id=%s job_id=%s report_entities=%d "
                "mapped_positions=%d skipped_unknown_zero_qty=%d persisted_positions=%d",
                command.aisle_id,
                command.job_id,
                len(command.report.get("entities") or []),
                len(mapped.positions),
                skipped_unknown_zero,
                persisted_positions,
            )
            logger.debug(
                "PersistAisleResult: saved %d positions for aisle %s",
                persisted_positions,
                command.aisle_id,
            )
            logger.debug(
                "PersistAisleResult: saved %d product_records for aisle %s",
                persisted_products,
                command.aisle_id,
            )
            logger.debug(
                "PersistAisleResult: saved %d evidences for aisle %s",
                persisted_evidences,
                command.aisle_id,
            )

            if self._raw_label_repo and mapped.raw_labels:
                self._raw_label_repo.save_many(mapped.raw_labels)
                logger.debug(
                    "PersistAisleResult: saved %d raw_labels for aisle %s",
                    len(mapped.raw_labels),
                    command.aisle_id,
                )

            if self._recompute_uc and inventory_id and self._raw_label_repo:
                result = self._recompute_uc.execute(
                    RecomputeConsolidatedCountsCommand(
                        inventory_id=inventory_id,
                        aisle_id=command.aisle_id,
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
            logger.exception(
                "PersistAisleResult failed for aisle %s job %s: %s",
                command.aisle_id,
                command.job_id,
                e,
            )
            raise


def should_persist_detected_position(sku: str | None, final_quantity: int | None) -> bool:
    """
    Persist all detections except the explicitly non-actionable case:
    unknown/empty SKU with exactly zero final quantity.
    """
    sku_norm = (sku or "").strip()
    is_unknown_sku = sku_norm == "" or sku_norm.upper() == "UNKNOWN"
    qty_norm = 0 if final_quantity is None else final_quantity
    return not (is_unknown_sku and qty_norm == 0)
