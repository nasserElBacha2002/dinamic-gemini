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
    FinalizationStageRecord,
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


def _valid_completed(rec: FinalizationStageRecord | None) -> bool:
    return rec is not None and rec.status == StageStatus.COMPLETED and rec.completed_at is not None


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
        authoritative_last_stage: FinalizationStage | None = None

        for stage in FINALIZATION_STAGE_ORDER:
            rec = stages.get(stage)
            if rec is not None and rec.status == StageStatus.COMPLETED:
                authoritative_last_stage = stage
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
            if all(_valid_completed(stages.get(stage)) for stage in FINALIZATION_STAGE_ORDER):
                finalization_status = FinalizationStatus.COMPLETED
                current_step = None
                last_completed = LastCompletedFinalizationStep.INVENTORY_RECONCILED
            else:
                finalization_status = FinalizationStatus.IN_PROGRESS

        job.finalization_status = finalization_status
        job.last_completed_finalization_step = last_completed
        job.current_finalization_step = current_step

        domain = stages.get(FinalizationStage.DOMAIN_RESULTS)
        job.domain_persisted_at = domain.completed_at if _valid_completed(domain) else None

        artifacts = stages.get(FinalizationStage.REQUIRED_ARTIFACTS)
        job.artifacts_published_at = (
            artifacts.completed_at if _valid_completed(artifacts) else None
        )

        if finalization_status == FinalizationStatus.COMPLETED:
            inv = stages.get(FinalizationStage.INVENTORY_RECONCILIATION)
            job.finalization_completed_at = (
                inv.completed_at if inv and inv.completed_at else self._latest_completed_at(stages)
            )
        else:
            job.finalization_completed_at = None

        if finalization_status == FinalizationStatus.FAILED:
            failed_rec = next(
                (
                    stages[stage]
                    for stage in FINALIZATION_STAGE_ORDER
                    if stages.get(stage)
                    and stages[stage].status in (StageStatus.FAILED, StageStatus.VERIFICATION_REQUIRED)
                ),
                None,
            )
            job.finalization_error_code = failed_rec.last_error_code if failed_rec else None
        else:
            job.finalization_error_code = None

        job.updated_at = now
        try:
            self._job_repo.save(job)
        except Exception as exc:
            logger.error(
                "finalization_summary_projection_failed job_id=%s authoritative_last_stage=%s "
                "projection_target_status=%s exception_type=%s error=%s",
                job_id,
                authoritative_last_stage.value if authoritative_last_stage else None,
                finalization_status.value,
                type(exc).__name__,
                exc,
            )

    def _latest_completed_at(
        self, stages: dict[FinalizationStage, FinalizationStageRecord]
    ):
        latest = None
        for stage in FINALIZATION_STAGE_ORDER:
            rec = stages.get(stage)
            if rec and rec.completed_at and (latest is None or rec.completed_at > latest):
                latest = rec.completed_at
        return latest
