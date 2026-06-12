"""Project authoritative stage evidence onto inventory_jobs summary fields — Phase 3.3."""

from __future__ import annotations

import logging

from src.application.ports.clock import Clock
from src.application.ports.finalization_stage_store import FinalizationStageStore
from src.application.ports.repositories import JobRepository
from src.domain.jobs.finalization import (
    CurrentFinalizationStep,
    FinalizationStatus,
    LastCompletedFinalizationStep,
)
from src.domain.jobs.finalization_evidence import (
    FINALIZATION_STAGE_ORDER,
    FinalizationStage,
    StageStatus,
)

logger = logging.getLogger(__name__)

_STAGE_TO_CURRENT: dict[FinalizationStage, CurrentFinalizationStep] = {
    FinalizationStage.DOMAIN_RESULTS: CurrentFinalizationStep.PERSIST_DOMAIN_RESULTS,
    FinalizationStage.REQUIRED_ARTIFACTS: CurrentFinalizationStep.PUBLISH_ARTIFACTS,
    FinalizationStage.JOB_TERMINALIZATION: CurrentFinalizationStep.TERMINALIZE_JOB,
    FinalizationStage.OPERATIONAL_PROMOTION: CurrentFinalizationStep.PROMOTE_OPERATIONAL_RESULT,
    FinalizationStage.AISLE_RECONCILIATION: CurrentFinalizationStep.UPDATE_AISLE,
    FinalizationStage.INVENTORY_RECONCILIATION: CurrentFinalizationStep.RECONCILE_INVENTORY,
}

_STAGE_TO_COMPLETED: dict[FinalizationStage, LastCompletedFinalizationStep] = {
    FinalizationStage.DOMAIN_RESULTS: LastCompletedFinalizationStep.DOMAIN_RESULTS_PERSISTED,
    FinalizationStage.REQUIRED_ARTIFACTS: LastCompletedFinalizationStep.ARTIFACTS_PUBLISHED,
    FinalizationStage.JOB_TERMINALIZATION: LastCompletedFinalizationStep.JOB_TERMINALIZED,
    FinalizationStage.OPERATIONAL_PROMOTION: (
        LastCompletedFinalizationStep.OPERATIONAL_RESULT_PROMOTED
    ),
    FinalizationStage.AISLE_RECONCILIATION: LastCompletedFinalizationStep.AISLE_UPDATED,
    FinalizationStage.INVENTORY_RECONCILIATION: LastCompletedFinalizationStep.INVENTORY_RECONCILED,
}


class FinalizationProjectionService:
    """Denormalized summary on ``inventory_jobs`` — authoritative data lives in stage store."""

    def __init__(
        self,
        *,
        job_repo: JobRepository,
        stage_store: FinalizationStageStore,
        clock: Clock,
    ) -> None:
        self._job_repo = job_repo
        self._stage_store = stage_store
        self._clock = clock

    def refresh_summary(self, job_id: str) -> None:
        job = self._job_repo.get_by_id(job_id)
        if job is None:
            return
        stages = {s.stage: s for s in self._stage_store.list_stages(job_id)}
        now = self._clock.now()
        last_completed = LastCompletedFinalizationStep.NONE
        current_step: CurrentFinalizationStep | None = None
        finalization_status = FinalizationStatus.IN_PROGRESS
        for stage in FINALIZATION_STAGE_ORDER:
            rec = stages.get(stage)
            if rec is None or rec.status in (StageStatus.UNKNOWN, StageStatus.NOT_STARTED):
                current_step = _STAGE_TO_CURRENT[stage]
                break
            if rec.status == StageStatus.COMPLETED:
                last_completed = _STAGE_TO_COMPLETED[stage]
                continue
            if rec.status in (StageStatus.FAILED, StageStatus.VERIFICATION_REQUIRED):
                finalization_status = FinalizationStatus.FAILED
                current_step = _STAGE_TO_CURRENT[stage]
                break
            if rec.status == StageStatus.CANCELED:
                finalization_status = FinalizationStatus.CANCELED
                current_step = _STAGE_TO_CURRENT[stage]
                break
            current_step = _STAGE_TO_CURRENT[stage]
            break
        else:
            finalization_status = FinalizationStatus.COMPLETED
            current_step = None
            last_completed = LastCompletedFinalizationStep.INVENTORY_RECONCILED

        job.finalization_status = finalization_status
        job.last_completed_finalization_step = last_completed
        job.current_finalization_step = current_step
        domain = stages.get(FinalizationStage.DOMAIN_RESULTS)
        if domain and domain.completed_at:
            job.domain_persisted_at = domain.completed_at
        artifacts = stages.get(FinalizationStage.REQUIRED_ARTIFACTS)
        if artifacts and artifacts.completed_at:
            job.artifacts_published_at = artifacts.completed_at
        if finalization_status == FinalizationStatus.COMPLETED:
            job.finalization_completed_at = now
        job.updated_at = now
        try:
            self._job_repo.save(job)
        except Exception as exc:
            logger.error(
                "finalization_summary_projection_failed job_id=%s error=%s",
                job_id,
                exc,
            )
