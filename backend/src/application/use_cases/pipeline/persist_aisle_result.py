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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.application.dto.mapped_aisle_result import MappedAisleResult
from src.application.ports.clock import Clock
from src.application.ports.hybrid_report_to_domain_mapper import HybridReportToDomainMapper
from src.application.ports.job_result_unit_of_work import (
    JobResultRepositories,
    JobResultUnitOfWork,
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
from src.domain.result_evidence.manifest_primary import primary_manifest_entry
from src.domain.traceability import TraceabilityStatus

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
    input_type: str | None = None


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
        report = prepare_hybrid_report_for_photo_persist(
            command.report,
            job_id=job_id,
            input_type=command.input_type,
            prompt_composition=command.prompt_composition,
        )
        mapped = self._map_hybrid(command, inventory_id, now, report=report)
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
                self._insert_mapped(uow, command, mapped)
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
        self,
        command: PersistAisleResultCommand,
        inventory_id: str,
        now: datetime,
        *,
        report: dict[str, Any],
    ) -> MappedAisleResult:
        return self._hybrid_mapper(
            aisle_id=command.aisle_id,
            report=report,
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
        uow: JobResultUnitOfWork,
        command: PersistAisleResultCommand,
        mapped: MappedAisleResult,
    ) -> None:
        repos = uow.repositories
        persisted_positions = 0
        skipped_unknown_zero = 0
        persisted_result_evidence_records: list = []
        job_id = (command.job_id or "").strip()
        for position, product, evidence, result_evidence in zip(
            mapped.positions,
            mapped.product_records,
            mapped.evidences,
            mapped.result_evidence_records,
        ):
            final_quantity = product.detected_quantity
            summary = position.detected_summary_json if isinstance(position.detected_summary_json, dict) else {}
            entity_type = summary.get("entity_type") if isinstance(summary.get("entity_type"), str) else None
            if not should_persist_detected_position(
                product.sku, final_quantity, entity_type=entity_type
            ):
                skipped_unknown_zero += 1
                continue

            source_asset_id = ""
            if isinstance(summary, dict):
                raw_asset = summary.get("source_asset_id") or summary.get("source_image_id")
                if isinstance(raw_asset, str):
                    source_asset_id = raw_asset.strip()
            if source_asset_id and job_id:
                # Same canonical applock as manual create — serializes concurrent writers.
                uow.acquire_image_result_lock(job_id=job_id, source_asset_id=source_asset_id)

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


def should_persist_detected_position(
    sku: str | None,
    final_quantity: int | None,
    *,
    entity_type: str | None = None,
) -> bool:
    """Persist physical inventory positions even when SKU/qty are unknown (operator review)."""
    et = (entity_type or "").strip().upper()
    if et in PHYSICAL_INVENTORY_ENTITY_TYPES:
        return True
    sku_norm = (sku or "").strip()
    is_unknown_sku = sku_norm == "" or sku_norm.upper() == "UNKNOWN"
    qty_norm = 0 if final_quantity is None else final_quantity
    return not (is_unknown_sku and qty_norm == 0)


PHYSICAL_INVENTORY_ENTITY_TYPES = frozenset({"PALLET", "EMPTY_PALLET", "LOOSE_BOXES"})

UNLABELED_SCAN_REVIEW_DISPLAY_LABEL = "Sin etiqueta legible — revisar"


def prepare_hybrid_report_for_photo_persist(
    report: dict[str, Any] | None,
    *,
    job_id: str,
    input_type: str | None,
    prompt_composition: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Ensure photo jobs yield at least one review row when the model returns no entities."""
    base: dict[str, Any] = dict(report) if isinstance(report, dict) else {}
    entities = base.get("entities")
    if not isinstance(entities, list):
        entities = []
    if entities:
        if base.get("total_entities_detected") is None:
            base["total_entities_detected"] = len(entities)
        return base
    if (input_type or "").strip().lower() != "photos":
        return base
    placeholder = {
        "entity_uid": f"{job_id}_no_readable_label",
        "entity_type": "PALLET",
        "model_entity_id": "UNLABELED_1",
        "internal_code": None,
        "product_label_quantity": None,
        "final_quantity": None,
        "confidence": 0.0,
        "count_status": "NEEDS_REVIEW",
        "review_display_label": UNLABELED_SCAN_REVIEW_DISPLAY_LABEL,
        "detection_outcome": "no_readable_label",
    }
    _enrich_unlabeled_placeholder_with_primary_manifest(placeholder, prompt_composition)
    return {
        **base,
        "entities": [placeholder],
        "total_entities_detected": 1,
    }


def _enrich_unlabeled_placeholder_with_primary_manifest(
    entity: dict[str, Any],
    prompt_composition: dict[str, Any] | None,
) -> None:
    """Attach job primary scan image ids so operators can review the source photo."""
    entry = primary_manifest_entry(prompt_composition)
    if entry is None:
        return
    entity["manifest_entry_id"] = entry.manifest_entry_id
    entity["resolved_manifest_entry_id"] = entry.manifest_entry_id
    entity["source_image_id"] = entry.source_image_id
    entity.setdefault("traceability_status", TraceabilityStatus.MISSING.value)


def hybrid_report_has_persistible_detections(
    report: dict[str, Any] | None,
    *,
    aisle_id: str,
    job_id: str,
    inventory_id: str,
    input_type: str | None = None,
    now: datetime | None = None,
) -> bool:
    """True when at least one hybrid_report entity would be persisted (mirrors skip rules)."""
    prepared = prepare_hybrid_report_for_photo_persist(
        report, job_id=job_id, input_type=input_type
    )
    if not isinstance(prepared, dict):
        return False
    entities = prepared.get("entities")
    if not isinstance(entities, list) or not entities:
        return False

    from src.infrastructure.pipeline.v3_report_mapper import map_hybrid_report_to_domain

    mapped = map_hybrid_report_to_domain(
        aisle_id,
        prepared,
        Path("."),
        "run",
        job_id,
        now or datetime.now(timezone.utc),
        inventory_id=inventory_id,
    )
    for position, product in zip(mapped.positions, mapped.product_records):
        summary = position.detected_summary_json if isinstance(position.detected_summary_json, dict) else {}
        entity_type = summary.get("entity_type") if isinstance(summary.get("entity_type"), str) else None
        if should_persist_detected_position(
            product.sku, product.detected_quantity, entity_type=entity_type
        ):
            return True
    return False
