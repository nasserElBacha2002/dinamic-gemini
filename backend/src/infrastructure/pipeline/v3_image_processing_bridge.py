"""Bridge Phase 2 aisle image orchestrator into V3JobExecutor (optional, flag-gated).

Wiring policy: when the app has resolved a SQL repository backend, the Phase 2
lease/state/attempt repositories must also be SQL (``require_sql=True``) — silently falling
back to in-memory repositories here would break cross-worker mutual exclusion (two worker
processes would each hold their own in-memory lease and both call the legacy provider). Callers
that cannot resolve the SQL repos for some reason must fail fast rather than degrade silently.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence

from src.application.errors import ImageProcessingRepositoryUnavailableError
from src.application.ports.clock import Clock
from src.application.ports.image_processing_repositories import (
    AssetProgressCounts,
    BatchProcessingAttemptRepository,
    JobAssetProcessingStateRepository,
    JobProcessingLeaseRepository,
    ProcessingAttemptRepository,
)
from src.application.ports.repositories import (
    EvidenceRepository,
    PositionRepository,
    ResultEvidenceRepository,
)
from src.application.services.image_processing.aisle_processing_orchestrator import (
    AisleOrchestratorOutcome,
    AisleProcessingOrchestrator,
    CodeScanAisleOutcome,
)
from src.application.services.image_processing.asset_result_coverage_resolver import (
    AssetResultCoverageResolver,
)
from src.application.services.image_processing.image_processing_orchestrator import (
    ImageProcessingOrchestrator,
)
from src.application.services.image_processing.legacy_llm_processing_strategy import (
    LegacyBatchRunner,
    LegacyLlmProcessingStrategy,
)
from src.application.services.image_processing.processing_strategy_resolver import (
    ProcessingStrategyResolver,
)
from src.domain.aisle.entities import Aisle
from src.domain.assets.entities import SourceAsset
from src.domain.jobs.entities import Job

logger = logging.getLogger(__name__)

_DEFAULT_LEASE_DURATION_SECONDS = 900
_DEFAULT_ABANDONED_TTL_SECONDS = 900


def _coerce_positive_int(value: object, *, default: int, label: str) -> int:
    """Coerce a settings-sourced duration to a positive int, falling back to ``default``.

    Guards against malformed/non-numeric configuration (e.g. an unset environment variable
    or a misconfigured settings object) reaching ``timedelta(seconds=...)`` deep inside the
    orchestrator, where it would otherwise raise a confusing ``TypeError``.
    """
    try:
        coerced = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        logger.warning("image_orchestrator.invalid_%s value=%r using_default=%s", label, value, default)
        return default
    if coerced <= 0:
        logger.warning("image_orchestrator.invalid_%s value=%r using_default=%s", label, value, default)
        return default
    return coerced


def build_default_aisle_processing_orchestrator(
    clock: Clock,
    *,
    attempts_enabled: bool,
    state_repo: JobAssetProcessingStateRepository | None,
    attempt_repo: ProcessingAttemptRepository | None,
    lease_repo: JobProcessingLeaseRepository | None,
    batch_attempt_repo: BatchProcessingAttemptRepository | None,
    result_evidence_repo: ResultEvidenceRepository,
    evidence_repo: EvidenceRepository,
    position_repo: PositionRepository,
    require_sql: bool = False,
    lease_duration_seconds: int = _DEFAULT_LEASE_DURATION_SECONDS,
    abandoned_processing_ttl_seconds: int = _DEFAULT_ABANDONED_TTL_SECONDS,
    coverage_positions_page_size: int = 2000,
) -> AisleProcessingOrchestrator:
    """Build the Phase 2 orchestrator from injected repos.

    ``require_sql=True`` means the caller resolved (or attempted to resolve) SQL-backed
    repositories elsewhere; any ``None`` here is treated as a hard failure
    (:class:`ImageProcessingRepositoryUnavailableError`) instead of a silent in-memory
    fallback, because in-memory lease/state repos are process-local and would defeat the
    exclusive-lease guarantee across worker processes.
    """
    lease_duration_seconds = _coerce_positive_int(
        lease_duration_seconds, default=_DEFAULT_LEASE_DURATION_SECONDS, label="lease_duration_seconds"
    )
    abandoned_processing_ttl_seconds = _coerce_positive_int(
        abandoned_processing_ttl_seconds,
        default=_DEFAULT_ABANDONED_TTL_SECONDS,
        label="abandoned_processing_ttl_seconds",
    )

    if require_sql:
        missing = [
            name
            for name, repo in (
                ("state_repo", state_repo),
                ("attempt_repo", attempt_repo),
                ("lease_repo", lease_repo),
                ("batch_attempt_repo", batch_attempt_repo),
            )
            if repo is None
        ]
        if missing:
            raise ImageProcessingRepositoryUnavailableError(
                f"require_sql=True but repositories unavailable: {', '.join(missing)}"
            )

    if state_repo is None or attempt_repo is None or lease_repo is None or batch_attempt_repo is None:
        from src.infrastructure.repositories.memory_batch_processing_attempt_repository import (
            MemoryBatchProcessingAttemptRepository,
        )
        from src.infrastructure.repositories.memory_job_asset_processing_state_repository import (
            MemoryJobAssetProcessingStateRepository,
        )
        from src.infrastructure.repositories.memory_job_processing_lease_repository import (
            MemoryJobProcessingLeaseRepository,
        )
        from src.infrastructure.repositories.memory_processing_attempt_repository import (
            MemoryProcessingAttemptRepository,
        )

        logger.warning("image_orchestrator.repos_falling_back_to_memory require_sql=%s", require_sql)
        state_repo = state_repo or MemoryJobAssetProcessingStateRepository()
        attempt_repo = attempt_repo or MemoryProcessingAttemptRepository()
        lease_repo = lease_repo or MemoryJobProcessingLeaseRepository()
        batch_attempt_repo = batch_attempt_repo or MemoryBatchProcessingAttemptRepository()

    image_orch = ImageProcessingOrchestrator(
        state_repo, attempt_repo, clock, attempts_enabled=attempts_enabled
    )
    coverage_resolver = AssetResultCoverageResolver(
        result_evidence_repo=result_evidence_repo,
        evidence_repo=evidence_repo,
        position_repo=position_repo,
        positions_page_size=coverage_positions_page_size,
    )
    return AisleProcessingOrchestrator(
        state_repo=state_repo,
        attempt_repo=attempt_repo,
        lease_repo=lease_repo,
        batch_attempt_repo=batch_attempt_repo,
        clock=clock,
        image_orchestrator=image_orch,
        strategy_resolver=ProcessingStrategyResolver(),
        legacy_strategy=LegacyLlmProcessingStrategy(),
        coverage_resolver=coverage_resolver,
        attempts_enabled=attempts_enabled,
        abandoned_processing_ttl_seconds=abandoned_processing_ttl_seconds,
        lease_duration_seconds=lease_duration_seconds,
    )


class _LazyPyzbarCodeScanner:
    """Defer pyzbar import to scan time so a missing libzbar surfaces per-asset.

    Constructing :class:`PyzbarCodeScanner` eagerly imports pyzbar and would raise at wiring
    time. Deferring lets :class:`CodeScanProcessingStrategy` catch the failure and record a
    FAILED_TECHNICAL asset result instead of aborting the whole worker at construction.
    """

    engine_name = "pyzbar"

    def __init__(self) -> None:
        self._delegate = None

    def _ensure(self):
        if self._delegate is None:
            from src.infrastructure.code_scanning.pyzbar_code_scanner import PyzbarCodeScanner

            self._delegate = PyzbarCodeScanner()
        return self._delegate

    def scan_asset(self, asset, content=None):
        return self._ensure().scan_asset(asset, content)


def build_default_code_scan_strategy(settings, artifact_store):
    """Build a :class:`CodeScanProcessingStrategy` from settings + artifact store."""
    from src.application.services.image_processing.code_detection_consolidator import (
        CodeDetectionConsolidator,
    )
    from src.application.services.image_processing.code_scan_processing_strategy import (
        CodeScanConfig,
        CodeScanProcessingStrategy,
    )
    from src.application.services.image_processing.encoded_label_payload_parser import (
        EncodedLabelPayloadParser,
    )
    from src.infrastructure.code_scanning.artifact_store_source_asset_content_reader import (
        ArtifactStoreSourceAssetContentReader,
    )

    parser = EncodedLabelPayloadParser(
        quantity_max=int(getattr(settings, "code_scan_quantity_max", 99999999)),
        allow_decimal_quantity=bool(
            getattr(settings, "code_scan_allow_decimal_quantity", False)
        ),
    )
    config = CodeScanConfig(
        quantity_max=int(getattr(settings, "code_scan_quantity_max", 99999999)),
        allow_decimal_quantity=bool(
            getattr(settings, "code_scan_allow_decimal_quantity", False)
        ),
        max_image_side=int(getattr(settings, "code_scan_max_image_side", 2048)),
        timeout_seconds=int(getattr(settings, "code_scan_timeout_seconds", 15)),
        enable_rotations=bool(getattr(settings, "code_scan_enable_rotations", True)),
        enable_preprocessing=bool(
            getattr(settings, "code_scan_enable_preprocessing", False)
        ),
        max_variants=int(getattr(settings, "code_scan_max_variants", 4)),
        max_technical_attempts=int(
            getattr(settings, "code_scan_max_technical_attempts", 2)
        ),
    )
    return CodeScanProcessingStrategy(
        scanner=_LazyPyzbarCodeScanner(),
        content_reader=ArtifactStoreSourceAssetContentReader(artifact_store),
        parser=parser,
        consolidator=CodeDetectionConsolidator(),
        config=config,
    )


def build_default_code_scan_persister(
    *, job_source_asset_repo, source_asset_repo, clock, unit_of_work_factory
):
    from src.application.services.image_processing.processing_result_persister import (
        ProcessingResultPersister,
    )

    return ProcessingResultPersister(
        job_source_asset_repo=job_source_asset_repo,
        source_asset_repo=source_asset_repo,
        clock=clock,
        unit_of_work_factory=unit_of_work_factory,
    )


def build_default_code_scan_orchestrator(
    clock: Clock,
    *,
    attempts_enabled: bool,
    state_repo: JobAssetProcessingStateRepository | None,
    attempt_repo: ProcessingAttemptRepository | None,
    lease_repo: JobProcessingLeaseRepository | None,
    batch_attempt_repo: BatchProcessingAttemptRepository | None,
    result_evidence_repo: ResultEvidenceRepository,
    evidence_repo: EvidenceRepository,
    position_repo: PositionRepository,
    code_scan_strategy,
    result_persister,
    code_scan_concurrency: int = 1,
    require_sql: bool = False,
    abandoned_processing_ttl_seconds: int = _DEFAULT_ABANDONED_TTL_SECONDS,
) -> AisleProcessingOrchestrator:
    """Build the Phase 3 orchestrator wired for CODE_SCAN SINGLE_ASSET processing.

    Reuses :class:`AisleProcessingOrchestrator` (same per-asset bookkeeping) but injects the
    code-scan strategy + result persister and a concurrency bound. No batch lease is used by
    the code-scan path, but the lease repo is still required by the shared constructor.
    """
    orch = build_default_aisle_processing_orchestrator(
        clock,
        attempts_enabled=attempts_enabled,
        state_repo=state_repo,
        attempt_repo=attempt_repo,
        lease_repo=lease_repo,
        batch_attempt_repo=batch_attempt_repo,
        result_evidence_repo=result_evidence_repo,
        evidence_repo=evidence_repo,
        position_repo=position_repo,
        require_sql=require_sql,
        abandoned_processing_ttl_seconds=abandoned_processing_ttl_seconds,
    )
    orch._code_scan_strategy = code_scan_strategy
    orch._result_persister = result_persister
    orch._code_scan_concurrency = max(1, int(code_scan_concurrency or 1))
    return orch


def run_orchestrated_code_scan(
    *,
    orchestrator: AisleProcessingOrchestrator,
    job: Job,
    aisle: Aisle,
    assets: Sequence[SourceAsset],
    pipeline_enabled: bool,
    orchestrator_enabled: bool,
    code_scan_processing_enabled: bool,
    is_cancelled: Callable[[], bool],
    worker_token: str,
    merge_progress: Callable[[AssetProgressCounts], None] | None = None,
) -> CodeScanAisleOutcome:
    return orchestrator.process_with_code_scan(
        job=job,
        aisle=aisle,
        assets=assets,
        pipeline_enabled=pipeline_enabled,
        orchestrator_enabled=orchestrator_enabled,
        code_scan_processing_enabled=code_scan_processing_enabled,
        is_cancelled=is_cancelled,
        worker_token=worker_token,
        merge_progress=merge_progress,
    )


def assets_with_result_from_evidence(
    result_evidence_repo: ResultEvidenceRepository, job_id: str
) -> frozenset[str]:
    """Legacy/audit-only helper (superseded by ``AssetResultCoverageResolver`` for synthesis)."""
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
    is_cancelled: Callable[[], bool],
    worker_token: str,
    batch_runner: LegacyBatchRunner,
) -> AisleOrchestratorOutcome:
    return orchestrator.process_with_legacy_batch(
        job=job,
        aisle=aisle,
        assets=assets,
        batch_runner=batch_runner,
        pipeline_enabled=pipeline_enabled,
        orchestrator_enabled=orchestrator_enabled,
        is_cancelled=is_cancelled,
        worker_token=worker_token,
    )


def attach_progress_to_job_result_json(job: Job, progress: AssetProgressCounts) -> Job:
    """Merge ``asset_progress`` into ``job.result_json`` without touching any other key.

    Callers must fetch ``job`` immediately before calling this (and save immediately after)
    to keep the read-modify-write race window minimal; ``JobRepository.save`` persists
    ``result_json`` verbatim and does not merge, so losing an intervening writer's other keys
    here would silently wipe them.
    """
    result_json = dict(job.result_json or {})
    result_json["asset_progress"] = progress_to_public_dict(progress)
    job.result_json = result_json
    return job
