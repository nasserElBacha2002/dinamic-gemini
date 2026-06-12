"""Write authoritative finalization stage evidence + summary projection — Phase 3.3."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from src.application.ports.artifact_manifest_store import ArtifactManifestStore
from src.application.ports.clock import Clock
from src.application.ports.finalization_stage_store import FinalizationStageStore
from src.application.services.finalization_projection_service import (
    FinalizationProjectionService,
)
from src.domain.jobs.artifact_policy import (
    ALL_EXPECTED_ARTIFACT_KINDS,
    OPTIONAL_ARTIFACT_KINDS,
    REQUIRED_ARTIFACT_KINDS,
    is_required_artifact_kind,
)
from src.domain.jobs.finalization import (
    CurrentFinalizationStep,
    LastCompletedFinalizationStep,
)
from src.domain.jobs.finalization_evidence import (
    EvidenceLevel,
    FinalizationStage,
    StageStatus,
)

logger = logging.getLogger(__name__)

_COMPLETED_TO_STAGE: dict[LastCompletedFinalizationStep, FinalizationStage] = {
    LastCompletedFinalizationStep.DOMAIN_RESULTS_PERSISTED: FinalizationStage.DOMAIN_RESULTS,
    LastCompletedFinalizationStep.ARTIFACTS_PUBLISHED: FinalizationStage.REQUIRED_ARTIFACTS,
    LastCompletedFinalizationStep.JOB_TERMINALIZED: FinalizationStage.JOB_TERMINALIZATION,
    LastCompletedFinalizationStep.OPERATIONAL_RESULT_PROMOTED: (
        FinalizationStage.OPERATIONAL_PROMOTION
    ),
    LastCompletedFinalizationStep.AISLE_UPDATED: FinalizationStage.AISLE_RECONCILIATION,
    LastCompletedFinalizationStep.INVENTORY_RECONCILED: (
        FinalizationStage.INVENTORY_RECONCILIATION
    ),
}

_CURRENT_TO_STAGE: dict[CurrentFinalizationStep, FinalizationStage] = {
    CurrentFinalizationStep.PERSIST_DOMAIN_RESULTS: FinalizationStage.DOMAIN_RESULTS,
    CurrentFinalizationStep.PUBLISH_ARTIFACTS: FinalizationStage.REQUIRED_ARTIFACTS,
    CurrentFinalizationStep.TERMINALIZE_JOB: FinalizationStage.JOB_TERMINALIZATION,
    CurrentFinalizationStep.PROMOTE_OPERATIONAL_RESULT: FinalizationStage.OPERATIONAL_PROMOTION,
    CurrentFinalizationStep.UPDATE_AISLE: FinalizationStage.AISLE_RECONCILIATION,
    CurrentFinalizationStep.RECONCILE_INVENTORY: FinalizationStage.INVENTORY_RECONCILIATION,
}


class FinalizationStageRecorder:
    def __init__(
        self,
        *,
        stage_store: FinalizationStageStore,
        projection: FinalizationProjectionService,
        manifest_store: ArtifactManifestStore | None,
        clock: Clock,
    ) -> None:
        self._stage_store = stage_store
        self._projection = projection
        self._manifest_store = manifest_store
        self._clock = clock

    def mark_in_progress(self, job_id: str, step: CurrentFinalizationStep) -> None:
        stage = _CURRENT_TO_STAGE[step]
        if step == CurrentFinalizationStep.PUBLISH_ARTIFACTS and self._manifest_store is not None:
            self._manifest_store.ensure_expected_entries(job_id, now=self._clock.now())
        self._transition(
            job_id=job_id,
            stage=stage,
            status=StageStatus.IN_PROGRESS,
            evidence_level=EvidenceLevel.POSITIVE_EVIDENCE_ONLY,
        )

    def mark_completed_for_step(
        self,
        job_id: str,
        completed: LastCompletedFinalizationStep,
        *,
        evidence_level: EvidenceLevel = EvidenceLevel.POSITIVE_EVIDENCE_ONLY,
        verification_source: str | None = None,
    ) -> None:
        stage = _COMPLETED_TO_STAGE[completed]
        existing = self._stage_store.get_stage(job_id, stage)
        if (
            existing
            and existing.status == StageStatus.COMPLETED
            and existing.evidence_level == EvidenceLevel.TRANSACTIONAL
        ):
            self._projection.refresh_summary(job_id)
            return
        now = self._clock.now()
        self._transition(
            job_id=job_id,
            stage=stage,
            status=StageStatus.COMPLETED,
            evidence_level=evidence_level,
            completed_at=now,
            verification_source=verification_source,
        )

    def mark_failed_for_step(
        self,
        job_id: str,
        step: CurrentFinalizationStep,
        *,
        error_code: str,
        metadata: dict[str, Any] | None = None,
        evidence_level: EvidenceLevel = EvidenceLevel.POSITIVE_EVIDENCE_ONLY,
    ) -> None:
        stage = _CURRENT_TO_STAGE[step]
        self._transition(
            job_id=job_id,
            stage=stage,
            status=StageStatus.FAILED,
            evidence_level=evidence_level,
            last_error_code=error_code,
            last_error_metadata=metadata,
        )

    def mark_verification_required(
        self,
        job_id: str,
        stage: FinalizationStage,
        *,
        error_code: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._transition(
            job_id=job_id,
            stage=stage,
            status=StageStatus.VERIFICATION_REQUIRED,
            evidence_level=EvidenceLevel.VERIFICATION_REQUIRED,
            last_error_code=error_code,
            last_error_metadata=metadata,
        )

    def record_artifact_manifest(
        self,
        job_id: str,
        durable_meta: dict[str, dict[str, Any]],
    ) -> None:
        if self._manifest_store is None:
            return
        now = self._clock.now()
        self._manifest_store.ensure_expected_entries(job_id, now=now)
        for kind in ALL_EXPECTED_ARTIFACT_KINDS:
            meta = durable_meta.get(kind)
            required = is_required_artifact_kind(kind)
            if meta and meta.get("storage_key"):
                self._manifest_store.mark_published(
                    job_id=job_id,
                    artifact_kind=kind,
                    storage_key=str(meta["storage_key"]),
                    size_bytes=meta.get("file_size_bytes"),
                    content_hash=meta.get("etag"),
                    required=required,
                    now=now,
                )
            elif required:
                self._manifest_store.mark_failed(
                    job_id=job_id,
                    artifact_kind=kind,
                    required=True,
                    error="required_artifact_not_uploaded",
                    now=now,
                )

    def _transition(
        self,
        *,
        job_id: str,
        stage: FinalizationStage,
        status: StageStatus,
        evidence_level: EvidenceLevel,
        completed_at: datetime | None = None,
        verification_source: str | None = None,
        last_error_code: str | None = None,
        last_error_metadata: dict[str, Any] | None = None,
    ) -> None:
        now = self._clock.now()
        existing = self._stage_store.get_stage(job_id, stage)
        try:
            self._stage_store.transition_stage(
                job_id=job_id,
                stage=stage,
                new_status=status,
                evidence_level=evidence_level,
                completed_at=completed_at,
                verified_at=completed_at if status == StageStatus.COMPLETED else None,
                verification_source=verification_source,
                last_error_code=last_error_code,
                last_error_metadata=last_error_metadata,
                expected_version=existing.version if existing else None,
                now=now,
            )
        except Exception as exc:
            logger.error(
                "finalization_stage_write_failed job_id=%s stage=%s error=%s",
                job_id,
                stage.value,
                exc,
            )
            raise
        try:
            self._projection.refresh_summary(job_id)
        except Exception as exc:
            logger.error(
                "finalization_projection_refresh_failed job_id=%s error=%s",
                job_id,
                exc,
            )
