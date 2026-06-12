"""Continue finalization from durable state using job_id only — Phase 3.5 corrections."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.application.ports.artifact_manifest_store import ArtifactManifestStore
from src.application.ports.clock import Clock
from src.application.ports.finalization_stage_store import FinalizationStageStore
from src.application.ports.repositories import AisleRepository, InventoryRepository, JobRepository
from src.application.services.finalization_projection_service import FinalizationProjectionService
from src.domain.jobs.artifact_manifest import ArtifactManifestStatus
from src.domain.jobs.artifact_policy import (
    ARTIFACT_KIND_HYBRID_REPORT_JSON,
    REQUIRED_ARTIFACT_KINDS,
)
from src.domain.jobs.entities import JobStatus
from src.domain.jobs.finalization import LastCompletedFinalizationStep
from src.domain.jobs.finalization_evidence import FinalizationStage, StageStatus
from src.infrastructure.pipeline.finalization_stage_recorder import FinalizationStageRecorder
from src.infrastructure.pipeline.job_finalization_tracker import JobFinalizationTracker
from src.infrastructure.pipeline.v3_job_execution_state import V3JobExecutionStateService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ContinuationResult:
    started: bool
    completed: bool
    reason: str | None = None


class AutomaticFinalizationContinuationUseCase:
    """Autonomous finalization continuation — no provider replay or in-memory worker context."""

    def __init__(
        self,
        *,
        job_repo: JobRepository,
        aisle_repo: AisleRepository,
        inventory_repo: InventoryRepository,
        manifest_store: ArtifactManifestStore,
        stage_store: FinalizationStageStore,
        state_service: V3JobExecutionStateService,
        clock: Clock,
    ) -> None:
        self._job_repo = job_repo
        self._aisle_repo = aisle_repo
        self._inventory_repo = inventory_repo
        self._manifest = manifest_store
        self._stage_store = stage_store
        self._state = state_service
        self._clock = clock

    def continue_finalization(self, job_id: str) -> ContinuationResult:
        job = self._job_repo.get_by_id(job_id)
        if job is None:
            return ContinuationResult(started=False, completed=False, reason="job_not_found")
        if job.status == JobStatus.SUCCEEDED:
            return ContinuationResult(started=False, completed=True, reason="already_succeeded")
        if job.last_completed_finalization_step == LastCompletedFinalizationStep.INVENTORY_RECONCILED:
            return ContinuationResult(started=False, completed=True, reason="already_completed")

        domain_stage = self._stage_store.get_stage(job_id, FinalizationStage.DOMAIN_RESULTS)
        if domain_stage is None or domain_stage.status != StageStatus.COMPLETED:
            return ContinuationResult(started=False, completed=False, reason="domain_not_completed")

        if not self._manifest.required_kinds_published(job_id):
            return ContinuationResult(
                started=False,
                completed=False,
                reason="required_artifacts_not_published",
            )

        for kind in REQUIRED_ARTIFACT_KINDS:
            manifest = self._manifest.get_entry(job_id, kind)
            if manifest is None or manifest.status != ArtifactManifestStatus.PUBLISHED:
                return ContinuationResult(
                    started=False,
                    completed=False,
                    reason="required_manifest_missing",
                )
            if manifest.verification_level and manifest.verification_level.value != "confirmed":
                if manifest.source_sha256 is None:
                    return ContinuationResult(
                        started=False,
                        completed=False,
                        reason="artifact_unverified",
                    )

        if job.target_type != "aisle" or not job.target_id:
            return ContinuationResult(started=False, completed=False, reason="invalid_target")
        aisle = self._aisle_repo.get_by_id(job.target_id)
        if aisle is None:
            return ContinuationResult(started=False, completed=False, reason="aisle_not_found")

        report_manifest = self._manifest.get_entry(job_id, ARTIFACT_KIND_HYBRID_REPORT_JSON)
        report_path = Path(
            report_manifest.storage_key if report_manifest and report_manifest.storage_key else "hybrid_report.json"
        )
        durable_artifacts = self._build_durable_artifacts(job_id)
        run_metadata = self._extract_run_metadata(job)

        projection = FinalizationProjectionService(
            job_repo=self._job_repo,
            stage_store=self._stage_store,
            clock=self._clock,
        )
        recorder = FinalizationStageRecorder(
            stage_store=self._stage_store,
            projection=projection,
            manifest_store=self._manifest,
            clock=self._clock,
        )
        tracker = JobFinalizationTracker(
            job_id=job_id,
            job_repo=self._job_repo,
            clock=self._clock,
            stage_recorder=recorder,
        )

        required_stage = self._stage_store.get_stage(job_id, FinalizationStage.REQUIRED_ARTIFACTS)
        if required_stage is None or required_stage.status != StageStatus.COMPLETED:
            tracker.record_artifacts_published(durable_artifacts=durable_artifacts)

        logger.info("artifact.automatic_continuation.started job_id=%s requested_by=system", job_id)
        self._state.finalize_success(
            job_id,
            aisle,
            report_path,
            tracker=tracker,
            run_metadata=run_metadata,
            durable_artifacts=durable_artifacts,
        )
        logger.info("artifact.automatic_continuation.completed job_id=%s", job_id)
        return ContinuationResult(started=True, completed=True)

    def _build_durable_artifacts(self, job_id: str) -> dict[str, dict[str, Any]]:
        durable: dict[str, dict[str, Any]] = {}
        for entry in self._manifest.list_entries(job_id):
            if entry.status != ArtifactManifestStatus.PUBLISHED or not entry.storage_key:
                continue
            durable[entry.artifact_kind] = {
                "storage_key": entry.storage_key,
                "file_size_bytes": entry.size_bytes,
                "etag": entry.storage_etag or entry.content_hash,
                "source_sha256": entry.source_sha256,
            }
        return durable

    @staticmethod
    def _extract_run_metadata(job) -> dict[str, Any] | None:
        if not job.result_json:
            return None
        meta: dict[str, Any] = {}
        for key in ("provider", "prompt_key", "prompt_version"):
            if key in job.result_json:
                meta[key] = job.result_json[key]
        return meta or None
