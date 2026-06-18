"""
PersistAisleResult use case — v3.0 Épica 6, v3.2.3 consolidation.

Maps a hybrid pipeline report to v3 domain entities and persists them.
v3.2.3: Also persists raw_labels and runs job-scoped recompute so
final quantity comes from normalized/final_count layer.

Phase 2 Part 2: delete-and-replace by ``job_id`` inside a transactional Unit of Work.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.application.dto.mapped_aisle_result import MappedAisleResult
from src.application.ports.clock import Clock
from src.application.ports.hybrid_report_to_domain_mapper import HybridReportToDomainMapper
from src.application.ports.job_result_unit_of_work import (
    JobResultRepositories,
    JobResultUnitOfWorkFactory,
)
from src.application.ports.job_scoped_recompute import JobScopedRecomputeFactory
from src.application.ports.repositories import (
    AisleRepository,
    EvidenceRepository,
    FinalCountRepository,
    NormalizedLabelRepository,
    PositionRepository,
    ProductRecordRepository,
    RawLabelRepository,
    ResultEvidenceRepository,
)
from src.application.use_cases.pipeline.recompute_consolidated_counts import (
    RecomputeConsolidatedCountsCommand,
)
from src.domain.jobs.finalization_evidence import EvidenceLevel, FinalizationStage

logger = logging.getLogger(__name__)

_BROAD_RECOMPUTE_SCOPES = frozenset({"all", "legacy_null"})


@dataclass
class PersistAisleResultCommand:
    aisle_id: str
    job_id: str
    report: dict
    run_dir: Path
    run_id: str = "run"
    provider: str | None = None
    model_name: str | None = None
    prompt_composition: dict | None = None


class PersistAisleResultUseCase:
    def __init__(
        self,
        position_repo: PositionRepository,
        product_record_repo: ProductRecordRepository,
        evidence_repo: EvidenceRepository,
        result_evidence_repo: ResultEvidenceRepository,
        clock: Clock,
        hybrid_mapper: HybridReportToDomainMapper,
        aisle_repo: AisleRepository,
        raw_label_repo: RawLabelRepository,
        normalized_label_repo: NormalizedLabelRepository,
        final_count_repo: FinalCountRepository,
        *,
        job_scoped_recompute_factory: JobScopedRecomputeFactory,
        job_result_uow_factory: JobResultUnitOfWorkFactory,
    ) -> None:
        if job_result_uow_factory is None:
            raise ValueError(
                "PersistAisleResultUseCase requires an explicit JobResultUnitOfWorkFactory"
            )
        if job_scoped_recompute_factory is None:
            raise ValueError(
                "PersistAisleResultUseCase requires an explicit JobScopedRecomputeFactory"
            )
        self._position_repo = position_repo
        self._product_record_repo = product_record_repo
        self._evidence_repo = evidence_repo
        self._result_evidence_repo = result_evidence_repo
        self._clock = clock
        self._hybrid_mapper = hybrid_mapper
        self._aisle_repo = aisle_repo
        self._raw_label_repo = raw_label_repo
        self._normalized_label_repo = normalized_label_repo
        self._final_count_repo = final_count_repo
        self._recompute_factory = job_scoped_recompute_factory
        self._uow_factory = job_result_uow_factory

    def execute(self, command: PersistAisleResultCommand) -> None:
        job_id = (command.job_id or "").strip()
        if not job_id:
            raise ValueError("PersistAisleResult requires a non-empty job_id")
        if job_id in _BROAD_RECOMPUTE_SCOPES:
            raise ValueError(f"PersistAisleResult rejects broad job_id scope: {job_id!r}")

        now = self._clock.now()
        inventory_id = self._inventory_id_for_aisle(command.aisle_id)
        mapped = self._map_hybrid(command, inventory_id, now)
        self._raise_if_mapped_lengths_mismatch(command, mapped)

        base_repos = JobResultRepositories(
            position_repo=self._position_repo,
            product_record_repo=self._product_record_repo,
            evidence_repo=self._evidence_repo,
            raw_label_repo=self._raw_label_repo,
            normalized_label_repo=self._normalized_label_repo,
            final_count_repo=self._final_count_repo,
            result_evidence_repo=self._result_evidence_repo,
        )

        with self._uow_factory(base_repos) as uow:
            active = uow.repositories
            try:
                before = uow.scope_store.delete_scope(
                    inventory_id=inventory_id,
                    aisle_id=command.aisle_id,
                    job_id=job_id,
                )
                logger.info(
                    "job_result_replacement started inventory_id=%s aisle_id=%s job_id=%s "
                    "prior_positions=%d",
                    inventory_id,
                    command.aisle_id,
                    job_id,
                    before.positions,
                )
                self._insert_mapped(active, command, mapped)
                self._recompute_job_scoped(active, command, inventory_id, job_id)
                writer = uow.finalization_evidence
                if writer is not None:
                    writer.mark_stage_completed(
                        job_id=job_id,
                        stage=FinalizationStage.DOMAIN_RESULTS,
                        evidence_level=EvidenceLevel.TRANSACTIONAL,
                        completed_at=now,
                        verification_source="persist_uow",
                    )
                uow.commit()
                logger.info(
                    "job_result_replacement committed inventory_id=%s aisle_id=%s job_id=%s",
                    inventory_id,
                    command.aisle_id,
                    job_id,
                )
            except Exception as e:
                logger.exception(
                    "job_result_replacement rolled back inventory_id=%s aisle_id=%s job_id=%s: %s",
                    inventory_id,
                    command.aisle_id,
                    job_id,
                    e,
                )
                raise

    def _inventory_id_for_aisle(self, aisle_id: str) -> str:
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
            provider=command.provider,
            model_name=command.model_name,
            prompt_composition=command.prompt_composition,
        )

    def _raise_if_mapped_lengths_mismatch(
        self, command: PersistAisleResultCommand, mapped: MappedAisleResult
    ) -> None:
        n_pos = len(mapped.positions)
        n_prod = len(mapped.product_records)
        n_evid = len(mapped.evidences)
        n_re = len(mapped.result_evidence_records)
        if n_pos != n_prod or n_prod != n_evid or n_evid != n_re:
            logger.error(
                "v3.persist_aisle_result mapped_length_mismatch aisle_id=%s job_id=%s "
                "positions=%d product_records=%d evidences=%d result_evidence_records=%d "
                "raw_labels=%d",
                command.aisle_id,
                command.job_id,
                n_pos,
                n_prod,
                n_evid,
                n_re,
                len(mapped.raw_labels),
            )
            raise ValueError(
                f"PersistAisleResult invariant broken: positions={n_pos} product_records={n_prod} "
                f"evidences={n_evid} result_evidence_records={n_re} (must be equal before zip)"
            )

    def _insert_mapped(
        self,
        repos: JobResultRepositories,
        command: PersistAisleResultCommand,
        mapped: MappedAisleResult,
    ) -> None:
        persisted_positions = 0
        skipped_unknown_zero = 0
        persisted_result_evidence_records: list = []
        for position, product, evidence, result_evidence in zip(
            mapped.positions,
            mapped.product_records,
            mapped.evidences,
            mapped.result_evidence_records,
        ):
            final_quantity = product.detected_quantity
            if not should_persist_detected_position(product.sku, final_quantity):
                skipped_unknown_zero += 1
                continue
            repos.position_repo.save(position)
            repos.product_record_repo.save(product)
            repos.evidence_repo.save(evidence)
            persisted_result_evidence_records.append(result_evidence)
            persisted_positions += 1

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

        if mapped.raw_labels:
            repos.raw_label_repo.save_many(mapped.raw_labels)

        if persisted_result_evidence_records:
            repos.result_evidence_repo.save_many(persisted_result_evidence_records)

    def _recompute_job_scoped(
        self,
        repos: JobResultRepositories,
        command: PersistAisleResultCommand,
        inventory_id: str,
        job_id: str,
    ) -> None:
        if job_id in _BROAD_RECOMPUTE_SCOPES:
            raise ValueError(
                "PersistAisleResult rejects broad recompute scope during operational persist"
            )
        recompute_cmd = RecomputeConsolidatedCountsCommand(
            inventory_id=inventory_id,
            aisle_id=command.aisle_id,
            apply_to_product_records=False,
            job_scope=job_id,
        )
        recompute = self._recompute_factory.create(repos)
        result = recompute.execute(recompute_cmd)
        logger.debug(
            "PersistAisleResult: recompute consolidated raw=%d normalized=%d final=%d",
            result.raw_count,
            result.normalized_count,
            result.final_count,
        )


def should_persist_detected_position(sku: str | None, final_quantity: int | None) -> bool:
    sku_norm = (sku or "").strip()
    is_unknown_sku = sku_norm == "" or sku_norm.upper() == "UNKNOWN"
    qty_norm = 0 if final_quantity is None else final_quantity
    return not (is_unknown_sku and qty_norm == 0)
