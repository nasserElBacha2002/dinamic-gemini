"""Bridge Phase 2 aisle image orchestrator into V3JobExecutor (optional, flag-gated)."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence

from src.application.ports.clock import Clock
from src.application.ports.image_processing_repositories import (
    AssetProgressCounts,
    JobAssetProcessingStateRepository,
    ProcessingAttemptRepository,
)
from src.application.ports.repositories import ResultEvidenceRepository
from src.application.services.image_processing.aisle_processing_orchestrator import (
    AisleOrchestratorOutcome,
    AisleProcessingOrchestrator,
)
from src.application.services.image_processing.image_processing_orchestrator import (
    ImageProcessingOrchestrator,
)
from src.application.services.image_processing.legacy_llm_processing_strategy import (
    LegacyBatchOutcome,
    LegacyLlmProcessingStrategy,
)
from src.application.services.image_processing.processing_strategy_resolver import (
    ProcessingStrategyResolver,
)
from src.domain.aisle.entities import Aisle
from src.domain.assets.entities import SourceAsset
from src.domain.jobs.entities import Job
from src.infrastructure.repositories.memory_job_asset_processing_state_repository import (
    MemoryJobAssetProcessingStateRepository,
)
from src.infrastructure.repositories.memory_processing_attempt_repository import (
    MemoryProcessingAttemptRepository,
)

logger = logging.getLogger(__name__)


def build_default_aisle_processing_orchestrator(
    clock: Clock,
    *,
    attempts_enabled: bool,
    state_repo: JobAssetProcessingStateRepository | None = None,
    attempt_repo: ProcessingAttemptRepository | None = None,
) -> AisleProcessingOrchestrator:
    states = state_repo or MemoryJobAssetProcessingStateRepository()
    attempts = attempt_repo or MemoryProcessingAttemptRepository()
    image_orch = ImageProcessingOrchestrator(
        states, attempts, clock, attempts_enabled=attempts_enabled
    )
    return AisleProcessingOrchestrator(
        state_repo=states,
        attempt_repo=attempts,
        clock=clock,
        image_orchestrator=image_orch,
        strategy_resolver=ProcessingStrategyResolver(),
        legacy_strategy=LegacyLlmProcessingStrategy(),
        attempts_enabled=attempts_enabled,
    )


def assets_with_result_from_evidence(
    result_evidence_repo: ResultEvidenceRepository, job_id: str
) -> frozenset[str]:
    rows = result_evidence_repo.list_by_job_id(job_id)
    return frozenset(
        (r.source_asset_id or "").strip()
        for r in rows
        if (r.source_asset_id or "").strip()
    )


def progress_to_public_dict(progress: AssetProgressCounts) -> dict[str, int]:
    return {
        "total": progress.total,
        "pending": progress.pending,
        "processing": progress.processing,
        "resolved": progress.resolved,
        "unrecognized": progress.unrecognized,
        "failed": progress.failed,
        "manual_review": progress.manual_review,
        "cancelled": progress.cancelled,
    }


def run_orchestrated_legacy_batch(
    *,
    orchestrator: AisleProcessingOrchestrator,
    job: Job,
    aisle: Aisle,
    assets: Sequence[SourceAsset],
    pipeline_enabled: bool,
    orchestrator_enabled: bool,
    cancel_requested: bool,
    batch_runner: Callable[..., LegacyBatchOutcome],
) -> AisleOrchestratorOutcome:
    orchestrator._legacy = LegacyLlmProcessingStrategy(batch_runner=batch_runner)
    return orchestrator.process_with_legacy_batch(
        job=job,
        aisle=aisle,
        assets=assets,
        runner_kwargs={},
        pipeline_enabled=pipeline_enabled,
        orchestrator_enabled=orchestrator_enabled,
        cancel_requested=cancel_requested,
    )


def attach_progress_to_job_result_json(job: Job, progress: AssetProgressCounts) -> Job:
    result_json = dict(job.result_json or {})
    result_json["asset_progress"] = progress_to_public_dict(progress)
    job.result_json = result_json
    return job
