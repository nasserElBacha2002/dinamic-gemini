"""Idempotent finalization continuation after required artifacts — Phase 3.5."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.application.ports.artifact_manifest_store import ArtifactManifestStore
from src.application.ports.finalization_stage_store import FinalizationStageStore
from src.application.ports.repositories import JobRepository
from src.domain.jobs.entities import JobStatus
from src.domain.jobs.finalization import LastCompletedFinalizationStep
from src.domain.jobs.finalization_evidence import FinalizationStage, StageStatus
from src.infrastructure.pipeline.job_finalization_tracker import JobFinalizationTracker
from src.infrastructure.pipeline.v3_job_execution_state import V3JobExecutionStateService

logger = logging.getLogger(__name__)


class ArtifactFinalizationContinuationCoordinator:
    """Continue terminalization → promotion → reconciliation without provider replay."""

    def __init__(
        self,
        *,
        job_repo: JobRepository,
        manifest_store: ArtifactManifestStore,
        stage_store: FinalizationStageStore,
        state_service: V3JobExecutionStateService,
    ) -> None:
        self._job_repo = job_repo
        self._manifest_store = manifest_store
        self._stage_store = stage_store
        self._state = state_service

    def continue_if_required_complete(
        self,
        *,
        job_id: str,
        aisle,
        report_path: Path,
        tracker: JobFinalizationTracker,
        run_metadata: dict[str, Any] | None,
        durable_artifacts: dict[str, dict[str, Any]],
    ) -> bool:
        if not self._manifest_store.required_kinds_published(job_id):
            return False
        job = self._job_repo.get_by_id(job_id)
        if job is not None and job.status == JobStatus.SUCCEEDED:
            return True
        if job is not None and job.last_completed_finalization_step == LastCompletedFinalizationStep.INVENTORY_RECONCILED:
            return True
        required_stage = self._stage_store.get_stage(job_id, FinalizationStage.REQUIRED_ARTIFACTS)
        if required_stage is not None and required_stage.status == StageStatus.COMPLETED:
            terminal_stage = self._stage_store.get_stage(job_id, FinalizationStage.JOB_TERMINALIZATION)
            if terminal_stage is not None and terminal_stage.status == StageStatus.COMPLETED:
                return True
        logger.info("artifact.finalization_continuation.started job_id=%s", job_id)
        self._state.finalize_success(
            job_id,
            aisle,
            report_path,
            tracker=tracker,
            run_metadata=run_metadata,
            durable_artifacts=durable_artifacts,
        )
        logger.info("artifact.finalization_continuation.completed job_id=%s", job_id)
        return True
