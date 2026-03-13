"""
PersistAisleResult use case — v3.0 Épica 6.

Maps a hybrid pipeline report to v3 domain entities and persists them.
Called after successful pipeline run; does not update job/aisle status (caller does that).

Atomicity: Saves positions, then product_records, then evidences. There is no
cross-repository transaction; if a later step fails, earlier steps are already
persisted. On any save failure we re-raise so the caller can mark the job/aisle
as failed. Partial result data may remain; monitor logs and job error_message
for investigation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from src.application.ports.repositories import (
    EvidenceRepository,
    PositionRepository,
    ProductRecordRepository,
)
from src.application.ports.clock import Clock
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
    ) -> None:
        self._position_repo = position_repo
        self._product_record_repo = product_record_repo
        self._evidence_repo = evidence_repo
        self._clock = clock

    def execute(self, command: PersistAisleResultCommand) -> None:
        now = self._clock.now()
        mapped = map_hybrid_report_to_domain(
            aisle_id=command.aisle_id,
            report=command.report,
            run_dir=command.run_dir,
            run_id=command.run_id,
            job_id=command.job_id,
            now=now,
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
        except Exception as e:
            logger.exception("PersistAisleResult failed for aisle %s job %s: %s", command.aisle_id, command.job_id, e)
            raise
