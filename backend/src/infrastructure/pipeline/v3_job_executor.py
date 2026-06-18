"""
V3 process_aisle job executor — Épica 6.

Thin coordinator: resolves aisle assets, delegates pipeline input + hybrid run, persists domain
results, durable artifacts, and job/aisle status via collaborators (Phase 2 split).
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from src.application.ports.artifact_manifest_store import ArtifactManifestStore
from src.application.ports.artifact_publication_outbox_store import ArtifactPublicationOutboxStore
from src.application.ports.artifact_staging_store import ArtifactStagingStore
from src.application.ports.clock import Clock
from src.application.ports.finalization_stage_store import FinalizationStageStore
from src.application.ports.job_result_unit_of_work import JobResultUnitOfWorkFactory
from src.application.ports.job_scoped_recompute import JobScopedRecomputeFactory
from src.application.ports.repositories import (
    AisleRepository,
    ClientSupplierRepository,
    EvidenceRepository,
    FinalCountRepository,
    InventoryRepository,
    JobRepository,
    NormalizedLabelRepository,
    PositionRepository,
    ProductRecordRepository,
    RawLabelRepository,
    SourceAssetRepository,
    SupplierPromptConfigRepository,
    SupplierReferenceImageRepository,
)
from src.application.services.aisle_analysis_context_builder import (
    AisleAnalysisContextBuilder,
)
from src.application.services.artifact_finalization_continuation import (
    ArtifactFinalizationContinuationCoordinator,
)
from src.application.services.artifact_publication_dispatcher import (
    ArtifactPublicationDispatcher,
    ArtifactSourceStagingFailedError,
)
from src.application.services.artifact_publication_retry_policy import DEFAULT_BACKOFF_SECONDS
from src.application.services.artifact_publication_state_reconciler import (
    ArtifactPublicationStateReconciler,
)
from src.application.services.automatic_finalization_continuation_use_case import (
    AutomaticFinalizationContinuationUseCase,
)
from src.application.services.finalization_projection_service import (
    FinalizationProjectionService,
)
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.services.job_engine_params import coerce_prompt_parity_mode
from src.application.services.operational_result_promotion_service import (
    OperationalResultPromotionService,
)
from src.application.services.supplier_prompt_resolver import (
    SupplierPromptResolution,
    SupplierPromptResolutionErrorCode,
    SupplierPromptResolver,
)
from src.application.services.supplier_reference_image_resolver import (
    SupplierReferenceImageResolver,
)
from src.application.use_cases.pipeline.persist_aisle_result import (
    PersistAisleResultCommand,
    PersistAisleResultUseCase,
)
from src.application.use_cases.pipeline.recompute_consolidated_counts import (
    RecomputeConsolidatedCountsUseCase,
)
from src.config import Settings, load_settings
from src.domain.aisle.entities import Aisle
from src.domain.jobs.artifact_manifest import ArtifactManifestStatus
from src.domain.jobs.artifact_policy import is_required_artifact_kind
from src.domain.jobs.entities import Job, JobStatus
from src.domain.jobs.finalization import (
    CurrentFinalizationStep,
    FinalizationErrorCode,
    LastCompletedFinalizationStep,
)
from src.infrastructure.pipeline.finalization_errors import (
    ArtifactPublishError,
    ArtifactPublishPartialError,
    ArtifactStoreUnavailableError,
)
from src.infrastructure.pipeline.finalization_stage_recorder import FinalizationStageRecorder
from src.infrastructure.pipeline.hybrid_report_to_domain_adapter import (
    default_map_hybrid_report_to_domain,
)
from src.infrastructure.pipeline.job_finalization_tracker import JobFinalizationTracker
from src.infrastructure.pipeline.v3_execution_artifacts_service import V3ExecutionArtifactsService
from src.infrastructure.pipeline.v3_job_execution_state import V3JobExecutionStateService
from src.infrastructure.pipeline.v3_process_aisle_pipeline_runner import (
    V3ProcessAislePipelineRunner,
    visual_reference_failure_metadata,
)
from src.infrastructure.pipeline.worker_durable_artifact_publisher import (
    DEFAULT_V3_WORKER_RUN_SEGMENT,
)
from src.io.logging import setup_logger
from src.jobs.worker_bootstrap import append_worker_bootstrap_event, checkpoint_v3_job_bootstrap
from src.pipeline.contracts.analysis_context import AnalysisContext, analysis_context_from_dict
from src.pipeline.errors import PipelineCancellationRequestedError
from src.pipeline.execution_log import ExecutionLogWriter, read_last_stage_error
from src.pipeline.hybrid_inventory_pipeline import HybridInventoryPipeline, PipelineRunResult
from src.pipeline.run_metadata import RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT

logger = logging.getLogger(__name__)

# Pipeline/output directory segment under {base}/{job_id}/; must match DEFAULT_V3_WORKER_RUN_SEGMENT.
RUN_ID = DEFAULT_V3_WORKER_RUN_SEGMENT


def _supplier_prompt_resolution_failure_message(resolution: SupplierPromptResolution) -> str:
    """Human-readable job failure text for observability (worker logs + job row)."""
    code = resolution.error_code or "UNKNOWN"
    base = (
        f"Supplier prompt resolution failed ({code}) "
        f"inventory_id={resolution.inventory_id} aisle_id={resolution.aisle_id}"
    )
    if code == SupplierPromptResolutionErrorCode.NO_ACTIVE_SUPPLIER_PROMPT_CONFIG:
        return (
            f"{base}: No active supplier_prompt_configs for client_supplier_id="
            f"{resolution.client_supplier_id!r} provider={resolution.provider_name!r} "
            f"model={resolution.model_name!r}. Configure and activate a supplier prompt "
            f"(Client → Supplier → Instrucciones / prompts)."
        )
    return f"{base}."


@dataclass(frozen=True)
class _V3PreparedJob:
    """Gate success: job marked running and ready for pipeline + persistence."""

    job: Job
    aisle: Aisle
    aisle_id: str
    assets: list[Any]


@dataclass(frozen=True)
class _V3PipelineInputRequest:
    """Bundle for building analysis context + FrameSource/pipeline input (B8.4 PLR0913)."""

    job_id: str
    aisle: Aisle
    aisle_id: str
    assets: list[Any]
    v3_base: Path
    job_dir: Path
    settings: Settings


@dataclass(frozen=True)
class _V3HybridRunParams:
    """Arguments for hybrid pipeline invocation + report load (B8.4 PLR0913)."""

    base_path: Path
    job_id: str
    job: Job
    aisle: Aisle
    aisle_id: str
    run_dir: Path
    settings: Settings
    log: Any
    pipeline_video_path: str
    job_input: Any
    analysis_context: AnalysisContext
    execution_observer: Callable[
        [str, str | None, str, dict[str, Any] | None],
        None,
    ]
    cancellation_checkpoint: Callable[[str, str | None, str], None]


@dataclass(frozen=True)
class _V3FinalizeAfterPipelineParams:
    """Persist + durable artifacts + mark_success (B8.4 PLR0913)."""

    job_id: str
    aisle: Aisle
    aisle_id: str
    run_dir: Path
    exec_log: ExecutionLogWriter
    result: PipelineRunResult
    report_path: Path
    report: dict[str, Any]
    cancellation_checkpoint: Callable[[str, str | None, str], None]
    cancel_event_emitted: dict[str, bool]


@dataclass(frozen=True)
class _V3RunMonitoringRequest:
    """Arguments for run_dir logger + heartbeat (B8.4 PLR0913)."""

    base_path: Path
    job_id: str
    job_dir: Path
    job: Job
    aisle: Aisle
    aisle_id: str


@dataclass
class _V3WorkerRuntimeHandles:
    """Run directory logger, execution log writer, and heartbeat thread (B8.4 PLR0915)."""

    run_dir: Path
    log: Any
    exec_log: ExecutionLogWriter
    stop_heartbeat: threading.Event
    heartbeat_thread: threading.Thread
    cancel_event_emitted: dict[str, bool]


class V3JobExecutor:
    """Execute v3 process_aisle jobs: load assets, run pipeline, persist results, update status."""

    def __init__(
        self,
        job_repo: JobRepository,
        aisle_repo: AisleRepository,
        source_asset_repo: SourceAssetRepository,
        position_repo: PositionRepository,
        product_record_repo: ProductRecordRepository,
        evidence_repo: EvidenceRepository,
        clock: Clock,
        inventory_repo: InventoryRepository,
        supplier_reference_image_repo: SupplierReferenceImageRepository,
        artifact_store=None,
        raw_label_repo: RawLabelRepository | None = None,
        normalized_label_repo: NormalizedLabelRepository | None = None,
        final_count_repo: FinalCountRepository | None = None,
        job_scoped_recompute_factory: JobScopedRecomputeFactory | None = None,
        job_result_uow_factory: JobResultUnitOfWorkFactory | None = None,
        recompute_consolidated_uc: RecomputeConsolidatedCountsUseCase | None = None,
        operational_promotion_service: OperationalResultPromotionService | None = None,
        client_supplier_repo: ClientSupplierRepository | None = None,
        supplier_prompt_config_repo: SupplierPromptConfigRepository | None = None,
        finalization_stage_store: FinalizationStageStore | None = None,
        artifact_manifest_store: ArtifactManifestStore | None = None,
        artifact_publication_outbox_store: ArtifactPublicationOutboxStore | None = None,
        artifact_staging_store: ArtifactStagingStore | None = None,
        artifact_publication_max_attempts: int = 5,
        artifact_publication_lease_seconds: int = 120,
        artifact_publication_backoff_seconds: tuple[int, ...] = DEFAULT_BACKOFF_SECONDS,
    ) -> None:
        self._job_repo = job_repo
        self._aisle_repo = aisle_repo
        self._inventory_repo = inventory_repo
        self._source_asset_repo = source_asset_repo
        self._artifact_store = artifact_store
        self._clock = clock
        inventory_status_reconciler = InventoryStatusReconciler(
            inventory_repo=inventory_repo,
            aisle_repo=aisle_repo,
            clock=clock,
        )
        self._state = V3JobExecutionStateService(
            job_repo=job_repo,
            aisle_repo=aisle_repo,
            inventory_repo=inventory_repo,
            clock=clock,
            inventory_status_reconciler=inventory_status_reconciler,
            operational_promotion_service=operational_promotion_service,
        )
        self._artifacts = V3ExecutionArtifactsService(artifact_store)
        supplier_resolver = SupplierReferenceImageResolver(supplier_reference_image_repo)
        context_builder = AisleAnalysisContextBuilder(supplier_resolver)
        self._pipeline_runner = V3ProcessAislePipelineRunner(
            supplier_reference_image_repo=supplier_reference_image_repo,
            artifact_store=artifact_store,
            context_builder=context_builder,
        )
        self._supplier_prompt_resolver: SupplierPromptResolver | None = None
        if client_supplier_repo is not None and supplier_prompt_config_repo is not None:
            self._supplier_prompt_resolver = SupplierPromptResolver(
                inventory_repo=inventory_repo,
                aisle_repo=aisle_repo,
                client_supplier_repo=client_supplier_repo,
                supplier_prompt_config_repo=supplier_prompt_config_repo,
            )
        if (
            raw_label_repo is None
            or normalized_label_repo is None
            or final_count_repo is None
            or aisle_repo is None
            or job_scoped_recompute_factory is None
            or job_result_uow_factory is None
        ):
            raise ValueError(
                "V3JobExecutor requires raw_label_repo, normalized_label_repo, "
                "final_count_repo, aisle_repo, job_scoped_recompute_factory, "
                "and job_result_uow_factory for PersistAisleResultUseCase"
            )
        self._persist_use_case = PersistAisleResultUseCase(
            position_repo=position_repo,
            product_record_repo=product_record_repo,
            evidence_repo=evidence_repo,
            clock=clock,
            hybrid_mapper=default_map_hybrid_report_to_domain,
            aisle_repo=aisle_repo,
            raw_label_repo=raw_label_repo,
            normalized_label_repo=normalized_label_repo,
            final_count_repo=final_count_repo,
            job_scoped_recompute_factory=job_scoped_recompute_factory,
            job_result_uow_factory=job_result_uow_factory,
        )
        _ = recompute_consolidated_uc
        self._heartbeat_interval_sec = 10
        self._stage_recorder: FinalizationStageRecorder | None = None
        if finalization_stage_store is not None:
            projection = FinalizationProjectionService(
                job_repo=job_repo,
                stage_store=finalization_stage_store,
                clock=clock,
            )
            self._stage_recorder = FinalizationStageRecorder(
                stage_store=finalization_stage_store,
                projection=projection,
                manifest_store=artifact_manifest_store,
                clock=clock,
            )
        self._artifact_manifest_store = artifact_manifest_store
        self._artifact_outbox_store = artifact_publication_outbox_store
        self._artifact_dispatcher: ArtifactPublicationDispatcher | None = None
        if (
            artifact_publication_outbox_store is not None
            and finalization_stage_store is not None
            and artifact_manifest_store is not None
            and artifact_store is not None
        ):
            continuation = ArtifactFinalizationContinuationCoordinator(
                job_repo=job_repo,
                manifest_store=artifact_manifest_store,
                stage_store=finalization_stage_store,
                state_service=self._state,
            )
            reconciler = ArtifactPublicationStateReconciler(
                outbox_store=artifact_publication_outbox_store,
                manifest_store=artifact_manifest_store,
                artifact_store=artifact_store,
                clock=clock,
            )
            automatic_continuation = AutomaticFinalizationContinuationUseCase(
                job_repo=job_repo,
                aisle_repo=aisle_repo,
                inventory_repo=inventory_repo,
                manifest_store=artifact_manifest_store,
                stage_store=finalization_stage_store,
                state_service=self._state,
                clock=clock,
            )
            self._artifact_dispatcher = ArtifactPublicationDispatcher(
                outbox_store=artifact_publication_outbox_store,
                manifest_store=artifact_manifest_store,
                stage_store=finalization_stage_store,
                artifact_store=artifact_store,
                stage_recorder=self._stage_recorder,
                continuation=continuation,
                automatic_continuation=automatic_continuation,
                staging_store=artifact_staging_store,
                reconciler=reconciler,
                clock=clock,
                lease_seconds=artifact_publication_lease_seconds,
                max_attempts=artifact_publication_max_attempts,
                backoff_seconds=artifact_publication_backoff_seconds,
            )

    def execute(self, base_path: Path, job_id: str) -> bool:
        """
        If job_id is a v3 process_aisle job: load aisle/assets, run pipeline, persist, update status; return True.
        Otherwise return False (caller may run legacy flow).
        """
        gate = self._v3_prepare_dispatch(job_id)
        if isinstance(gate, bool):
            return gate
        return self._v3_run_job_body(base_path, job_id, gate)

    def _v3_should_skip_for_terminal_job_status(self, job: Job, job_id: str) -> bool:
        """True when execute() must return True without running the pipeline body."""
        if job.status == JobStatus.CANCELED:
            logger.info("v3 job %s already canceled, skip", job_id)
            return True
        if job.status == JobStatus.CANCEL_REQUESTED:
            logger.info("v3 job %s cancel requested before start; marking canceled", job_id)
            self._state.cancel_job(job, "Job canceled before execution", now=self._clock.now())
            return True
        if job.status != JobStatus.STARTING:
            logger.warning(
                "v3 job %s invalid status for execution (status=%s), skip", job_id, job.status.value
            )
            return True
        return False

    def _v3_prepare_dispatch(self, job_id: str) -> bool | _V3PreparedJob:
        """Load job/aisle/assets; return False if not v3, True if terminal skip, else prepared context."""
        job = self._job_repo.get_by_id(job_id)
        logger.info("v3 dispatch: job_id=%s found=%s", job_id, job is not None)
        if job is None or job.job_type != "process_aisle":
            if job is not None:
                logger.info(
                    "v3 dispatch skipped: job_id=%s job_type=%s target_type=%s target_id=%s",
                    job_id,
                    job.job_type,
                    job.target_type,
                    job.target_id,
                )
            return False
        logger.info(
            "v3 dispatch accepted: job_id=%s job_type=%s target_type=%s target_id=%s status=%s",
            job_id,
            job.job_type,
            job.target_type,
            job.target_id,
            job.status.value,
        )
        if self._v3_should_skip_for_terminal_job_status(job, job_id):
            return True

        payload = job.payload_json or {}
        aisle_id = payload.get("aisle_id")
        if not aisle_id:
            self._state.fail_job(job_id, "Missing aisle_id in payload")
            return True

        aisle = self._aisle_repo.get_by_id(aisle_id)
        if aisle is None:
            self._state.fail_job(job_id, f"Aisle not found: {aisle_id}")
            return True
        logger.info(
            "v3 target resolved: job_id=%s job_type=%s target_type=%s target_id=%s inventory_id=%s aisle_id=%s",
            job_id,
            job.job_type,
            job.target_type,
            job.target_id,
            aisle.inventory_id,
            aisle_id,
        )
        assets = list(self._source_asset_repo.list_by_aisle(aisle_id))
        checkpoint_v3_job_bootstrap(
            job_id=job_id,
            execution_id=job.execution_id,
            substep="executor_bootstrap_completed",
        )
        if not assets:
            self._state.fail_job_and_aisle(job_id, aisle, "No source assets for aisle")
            return True

        now = self._clock.now()
        logger.info(
            "v3 mark running: job_id=%s job_type=%s target_type=%s target_id=%s inventory_id=%s aisle_id=%s",
            job_id,
            job.job_type,
            job.target_type,
            job.target_id,
            aisle.inventory_id,
            aisle_id,
        )
        append_worker_bootstrap_event(
            job_id=job_id,
            execution_id=job.execution_id,
            event="worker.starting_to_running_transition_started",
            details={"inventory_id": aisle.inventory_id, "aisle_id": aisle_id},
        )
        self._state.mark_running(job_id, aisle, now)
        append_worker_bootstrap_event(
            job_id=job_id,
            execution_id=job.execution_id,
            event="worker.starting_to_running_transition_completed",
            details={"inventory_id": aisle.inventory_id, "aisle_id": aisle_id},
        )
        return _V3PreparedJob(job=job, aisle=aisle, aisle_id=aisle_id, assets=assets)

    def _v3_resolve_pipeline_inputs_or_abort(
        self, req: _V3PipelineInputRequest
    ) -> tuple[AnalysisContext, Any, str | None] | None:
        """Build analysis context + pipeline input. None => fail_job_and_aisle already applied."""
        analysis_context: AnalysisContext | None = None
        try:
            inv = self._inventory_repo.get_by_id(req.aisle.inventory_id)
            inv_client = (inv.client_id or "").strip() if inv is not None else ""
            analysis_context = self._pipeline_runner.build_analysis_context(
                req.aisle,
                inventory_client_id=inv_client or None,
            )
            job_input, video_path = self._pipeline_runner.build_pipeline_input(
                req.assets,
                req.v3_base,
                req.job_dir,
                req.job_id,
                analysis_context=analysis_context,
                aisle=req.aisle,
                run_id=RUN_ID,
                legacy_local_read_enabled=req.settings.artifact_storage_legacy_local_read_enabled,
            )
            resolved_analysis_context = analysis_context_from_dict(
                (job_input.metadata or {}).get("analysis_context")
            )
            if resolved_analysis_context is not None:
                analysis_context = resolved_analysis_context
            logger.info(
                "v3 pipeline input ready: job_id=%s inventory_id=%s aisle_id=%s input_type=%s video_path=%s",
                req.job_id,
                req.aisle.inventory_id,
                req.aisle_id,
                job_input.input_type,
                video_path or "",
            )
        except Exception as e:
            logger.exception("v3 job %s: build pipeline input failed: %s", req.job_id, e)
            if analysis_context is not None and analysis_context.visual_references:
                job = self._job_repo.get_by_id(req.job_id)
                if job is not None:
                    result_json = dict(job.result_json or {})
                    result_json[RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT] = (
                        visual_reference_failure_metadata(
                            analysis_context,
                            str(e),
                        )
                    )
                    job.result_json = result_json
                    self._job_repo.save(job)
            self._state.fail_job_and_aisle(req.job_id, req.aisle, str(e))
            return None

        assert analysis_context is not None
        return analysis_context, job_input, video_path

    def _v3_hybrid_run_and_load_report(
        self, p: _V3HybridRunParams
    ) -> tuple[dict[str, Any], PipelineRunResult, Path] | None:
        """Run hybrid pipeline and load hybrid_report.json. None => failure handled (caller returns True)."""
        p.cancellation_checkpoint(
            "Pipeline",
            "pre_pipeline",
            "Job canceled before pipeline execution",
        )
        logger.info(
            "v3 executor start: job_id=%s job_type=%s target_type=%s target_id=%s inventory_id=%s aisle_id=%s",
            p.job_id,
            p.job.job_type,
            p.job.target_type,
            p.job.target_id,
            p.aisle.inventory_id,
            p.aisle_id,
        )
        pipeline = HybridInventoryPipeline()
        pipeline_provider_name = (p.job.provider_name or "").strip() or None
        job_model = (p.job.model_name or "").strip() or None
        job_prompt = (p.job.prompt_key or "").strip() or None
        job_prompt_version = (p.job.prompt_version or "").strip() or None
        job_prompt_parity_mode = coerce_prompt_parity_mode(p.job.engine_params_json)
        supplier_prompt_resolution = None
        spr = self._supplier_prompt_resolver
        if spr is not None:
            supplier_prompt_resolution = spr.resolve(
                inventory_id=p.aisle.inventory_id,
                aisle_id=p.aisle_id,
                provider_name=pipeline_provider_name,
                model_name=job_model,
                allow_missing_supplier_prompt_fallback=bool(
                    getattr(p.settings, "v3_allow_missing_supplier_prompt_fallback", False)
                ),
            )
            if supplier_prompt_resolution.resolution_status == "error":
                err_code = supplier_prompt_resolution.error_code or "UNKNOWN"
                logger.error(
                    "v3 supplier prompt resolution error job_id=%s inventory_id=%s aisle_id=%s code=%s",
                    p.job_id,
                    p.aisle.inventory_id,
                    p.aisle_id,
                    err_code,
                )
                self._state.fail_job_and_aisle(
                    p.job_id,
                    p.aisle,
                    _supplier_prompt_resolution_failure_message(supplier_prompt_resolution),
                )
                return None
        result = self._pipeline_runner.run_hybrid_pipeline(
            pipeline=pipeline,
            video_path=p.pipeline_video_path,
            job_id=p.job_id,
            base_path=p.base_path,
            run_id=RUN_ID,
            settings=p.settings,
            job_input=p.job_input,
            analysis_context=p.analysis_context,
            log=p.log,
            execution_observer=p.execution_observer,
            cancellation_checkpoint=p.cancellation_checkpoint,
            pipeline_provider_name=pipeline_provider_name,
            job_model_name=job_model,
            job_prompt_key=job_prompt,
            job_prompt_version=job_prompt_version,
            job_prompt_parity_mode=job_prompt_parity_mode,
            supplier_prompt_resolution=supplier_prompt_resolution,
        )
        logger.info(
            "v3 executor finished: job_id=%s exit_code=%s inventory_id=%s aisle_id=%s",
            p.job_id,
            result.exit_code,
            p.aisle.inventory_id,
            p.aisle_id,
        )
        if result.exit_code != 0:
            last_error = read_last_stage_error(p.run_dir)
            if last_error:
                error_message = f"{last_error} (exit code {result.exit_code})"
            else:
                error_message = f"Pipeline exited with code {result.exit_code}"
            self._state.fail_job_and_aisle(p.job_id, p.aisle, error_message)
            return None

        p.cancellation_checkpoint(
            "Pipeline",
            "post_pipeline",
            "Job canceled after pipeline execution",
        )

        report_path = p.run_dir / "hybrid_report.json"
        if not report_path.exists():
            self._state.fail_job_and_aisle(
                p.job_id, p.aisle, "Reporting error: Pipeline did not produce hybrid_report.json"
            )
            return None

        with open(report_path, encoding="utf-8") as f:
            report = json.load(f)
        return report, result, report_path

    def _v3_persist_durables_and_mark_success(self, p: _V3FinalizeAfterPipelineParams) -> bool:
        """Persist domain, upload durables, finalize success. True => caller must return True (failure)."""
        tracker = JobFinalizationTracker(
            job_repo=self._job_repo,
            clock=self._clock,
            job_id=p.job_id,
            stage_recorder=self._stage_recorder,
        )
        tracker.begin()
        try:
            return self._v3_persist_durables_and_mark_success_body(p, tracker)
        except PipelineCancellationRequestedError as cancel_exc:
            if tracker.last_completed == LastCompletedFinalizationStep.DOMAIN_RESULTS_PERSISTED:
                self._state.cancel_finalization_after_domain_commit(
                    p.job_id,
                    p.aisle,
                    str(cancel_exc),
                    tracker=tracker,
                    exec_log=p.exec_log,
                    cancel_event_emitted=p.cancel_event_emitted,
                )
            else:
                self._state.cancel_job_and_aisle(
                    p.job_id,
                    p.aisle,
                    str(cancel_exc),
                    exec_log=p.exec_log,
                    cancel_event_emitted=p.cancel_event_emitted,
                    tracker=tracker,
                )
            return True

    def _v3_persist_durables_and_mark_success_body(
        self,
        p: _V3FinalizeAfterPipelineParams,
        tracker: JobFinalizationTracker,
    ) -> bool:
        p.exec_log.info("Persist", "Persist started", payload={"aisle_id": p.aisle_id})
        try:
            p.cancellation_checkpoint(
                "Persist",
                "pre_persist",
                "Job canceled before persistence",
            )
            self._persist_use_case.execute(
                PersistAisleResultCommand(
                    aisle_id=p.aisle_id,
                    job_id=p.job_id,
                    report=p.report,
                    run_dir=p.run_dir,
                    run_id=RUN_ID,
                )
            )
        except PipelineCancellationRequestedError:
            raise
        except Exception as persist_e:
            p.exec_log.error(
                "Persist",
                f"Persist failed: {persist_e}",
                payload={"error": str(persist_e)[:500]},
            )
            self._state.fail_finalization_and_aisle(
                p.job_id,
                p.aisle,
                tracker=tracker,
                error_code=FinalizationErrorCode.DOMAIN_PERSISTENCE_FAILED,
                current_step=CurrentFinalizationStep.PERSIST_DOMAIN_RESULTS,
                message=f"Persist: {persist_e}",
                metadata={"exception_type": type(persist_e).__name__},
            )
            return True

        try:
            # Post-UoW marker — see JobFinalizationTracker docstring for crash-window note.
            tracker.record_domain_persisted()
            p.exec_log.info("Persist", "Persist completed")
        except Exception as marker_e:
            p.exec_log.error(
                "Persist",
                f"Domain marker write failed: {marker_e}",
                payload={"error": str(marker_e)[:500]},
            )
            self._state.fail_finalization_and_aisle(
                p.job_id,
                p.aisle,
                tracker=tracker,
                error_code=FinalizationErrorCode.FINALIZATION_METADATA_WRITE_FAILED,
                current_step=CurrentFinalizationStep.PERSIST_DOMAIN_RESULTS,
                message=f"Domain marker write failed: {marker_e}",
                metadata={
                    "domain_commit_completed": True,
                    "marker_write_completed": False,
                    "verification_required": True,
                    "failed_marker": "DOMAIN_RESULTS_PERSISTED",
                    "exception_type": type(marker_e).__name__,
                },
            )
            return True

        logger.info(
            "v3_job_domain_persist_complete job_id=%s aisle_id=%s next_step=durable_artifact_upload",
            p.job_id,
            p.aisle_id,
        )

        try:
            self._artifacts.require_store()
        except ArtifactStoreUnavailableError as store_err:
            msg = str(store_err)
            logger.error("v3_job_id=%s %s", p.job_id, msg)
            p.exec_log.error("Artifacts", msg)
            self._state.fail_finalization_and_aisle(
                p.job_id,
                p.aisle,
                tracker=tracker,
                error_code=FinalizationErrorCode.ARTIFACT_STORE_UNAVAILABLE,
                current_step=CurrentFinalizationStep.PUBLISH_ARTIFACTS,
                message=msg,
            )
            return True

        durable_meta: dict[str, dict[str, Any]] | None = None
        try:
            p.cancellation_checkpoint(
                "Artifacts",
                "pre_upload",
                "Job canceled before artifact upload",
            )
            if self._artifact_dispatcher is not None:
                return self._publish_artifacts_via_outbox(p, tracker)
            durable_meta = self._artifacts.publish_worker_durables(
                job_id=p.job_id,
                run_segment=RUN_ID,
                run_dir=p.run_dir,
            )
            logger.info(
                "worker_durable_artifacts_ready_for_job_metadata job_id=%s kinds=%s",
                p.job_id,
                sorted(durable_meta.keys()),
            )
        except PipelineCancellationRequestedError:
            raise
        except ArtifactPublishPartialError as partial_exc:
            logger.exception(
                "worker_durable_artifact_publish_partial job_id=%s failed_kind=%s",
                p.job_id,
                partial_exc.failed_kind,
            )
            p.exec_log.error(
                "Artifacts",
                f"Partial durable artifact upload: {partial_exc}",
                payload={"error": str(partial_exc)[:500]},
            )
            self._state.fail_finalization_and_aisle(
                p.job_id,
                p.aisle,
                tracker=tracker,
                error_code=FinalizationErrorCode.ARTIFACT_PUBLISH_PARTIAL,
                current_step=CurrentFinalizationStep.PUBLISH_ARTIFACTS,
                message=f"Durable artifact upload partial failure: {partial_exc}",
                metadata={
                    "failed_kind": partial_exc.failed_kind,
                    "published_artifacts": partial_exc.published,
                },
            )
            return True
        except (ArtifactPublishError, FileNotFoundError) as artifact_exc:
            logger.exception(
                "worker_durable_artifact_upload_failed job_id=%s",
                p.job_id,
            )
            p.exec_log.error(
                "Artifacts",
                f"Durable artifact upload failed: {artifact_exc}",
                payload={"error": str(artifact_exc)[:500]},
            )
            self._state.fail_finalization_and_aisle(
                p.job_id,
                p.aisle,
                tracker=tracker,
                error_code=FinalizationErrorCode.ARTIFACT_PUBLISH_FAILED,
                current_step=CurrentFinalizationStep.PUBLISH_ARTIFACTS,
                message=f"Durable artifact upload failed: {artifact_exc}",
            )
            return True
        except Exception as artifact_exc:
            logger.exception(
                "worker_durable_artifact_publish_unexpected job_id=%s",
                p.job_id,
            )
            p.exec_log.error(
                "Artifacts",
                f"Durable artifact upload failed: {artifact_exc}",
                payload={"error": str(artifact_exc)[:500]},
            )
            self._state.fail_finalization_and_aisle(
                p.job_id,
                p.aisle,
                tracker=tracker,
                error_code=FinalizationErrorCode.ARTIFACT_PUBLISH_FAILED,
                current_step=CurrentFinalizationStep.PUBLISH_ARTIFACTS,
                message=f"Durable artifact upload failed: {artifact_exc}",
                metadata={"exception_type": type(artifact_exc).__name__},
            )
            return True

        assert durable_meta is not None
        try:
            tracker.record_artifacts_published(durable_artifacts=durable_meta)
        except Exception as marker_e:
            p.exec_log.error(
                "Artifacts",
                f"Artifact marker write failed: {marker_e}",
                payload={"error": str(marker_e)[:500]},
            )
            self._state.fail_finalization_and_aisle(
                p.job_id,
                p.aisle,
                tracker=tracker,
                error_code=FinalizationErrorCode.FINALIZATION_METADATA_WRITE_FAILED,
                current_step=CurrentFinalizationStep.PUBLISH_ARTIFACTS,
                message=f"Artifact marker write failed: {marker_e}",
                metadata={
                    "artifact_upload_completed": True,
                    "marker_write_completed": False,
                    "verification_required": True,
                    "failed_marker": "ARTIFACTS_PUBLISHED",
                    "published_artifact_kinds": sorted(durable_meta.keys()),
                    "exception_type": type(marker_e).__name__,
                },
            )
            return True

        try:
            self._state.finalize_success(
                p.job_id,
                p.aisle,
                p.report_path,
                tracker=tracker,
                run_metadata=p.result.run_metadata,
                durable_artifacts=durable_meta,
            )
        except Exception:
            logger.exception("v3_job_finalization_terminal_failed job_id=%s", p.job_id)
            return True

        logger.info(
            "v3 mark success: job_id=%s inventory_id=%s aisle_id=%s report_path=%s",
            p.job_id,
            p.aisle.inventory_id,
            p.aisle_id,
            str(p.report_path),
        )
        return False

    def _publish_artifacts_via_outbox(
        self,
        p: _V3FinalizeAfterPipelineParams,
        tracker: JobFinalizationTracker,
    ) -> bool:
        assert self._artifact_dispatcher is not None
        try:
            self._artifact_dispatcher.register_publication_work(
                job_id=p.job_id,
                run_segment=RUN_ID,
                run_dir=p.run_dir,
            )
        except ArtifactSourceStagingFailedError as exc:
            staging_code = getattr(exc, "error_code", "ARTIFACT_STAGING_FAILED")
            p.exec_log.error(
                "Artifacts",
                f"Required artifact staging failed: {exc}",
                payload={
                    "error": str(exc)[:500],
                    "staging_error_code": staging_code,
                },
            )
            self._state.fail_finalization_and_aisle(
                p.job_id,
                p.aisle,
                tracker=tracker,
                error_code=FinalizationErrorCode.ARTIFACT_SOURCE_STAGING_FAILED,
                current_step=CurrentFinalizationStep.PUBLISH_ARTIFACTS,
                message=f"Required artifact staging failed: {exc}",
                metadata={
                    "verification_required": True,
                    "staging_error_code": staging_code,
                },
            )
            return True
        try:
            dispatch_result = self._artifact_dispatcher.dispatch_job(
                job_id=p.job_id,
                run_segment=RUN_ID,
                run_dir=p.run_dir,
                tracker=tracker,
                continuation_aisle=p.aisle,
                report_path=p.report_path,
                run_metadata=p.result.run_metadata,
            )
        except Exception as exc:
            job = self._job_repo.get_by_id(p.job_id)
            if job is not None and job.finalization_error_code:
                return True
            manifest = self._artifact_manifest_store
            if manifest is not None and manifest.required_kinds_published(p.job_id):
                published_kinds = sorted(
                    entry.artifact_kind
                    for entry in manifest.list_entries(p.job_id)
                    if entry.status == ArtifactManifestStatus.PUBLISHED
                )
                p.exec_log.error(
                    "Artifacts",
                    f"Artifact marker write failed: {exc}",
                    payload={"error": str(exc)[:500]},
                )
                self._state.fail_finalization_and_aisle(
                    p.job_id,
                    p.aisle,
                    tracker=tracker,
                    error_code=FinalizationErrorCode.FINALIZATION_METADATA_WRITE_FAILED,
                    current_step=CurrentFinalizationStep.PUBLISH_ARTIFACTS,
                    message=f"Artifact marker write failed: {exc}",
                    metadata={
                        "artifact_upload_completed": True,
                        "marker_write_completed": False,
                        "verification_required": True,
                        "failed_marker": "ARTIFACTS_PUBLISHED",
                        "published_artifact_kinds": published_kinds,
                        "exception_type": type(exc).__name__,
                    },
                )
                return True
            p.exec_log.error(
                "Artifacts",
                f"Artifact publication dispatch failed: {exc}",
                payload={"error": str(exc)[:500]},
            )
            self._state.fail_finalization_and_aisle(
                p.job_id,
                p.aisle,
                tracker=tracker,
                error_code=FinalizationErrorCode.FINALIZATION_METADATA_WRITE_FAILED,
                current_step=CurrentFinalizationStep.PUBLISH_ARTIFACTS,
                message=f"Artifact publication dispatch failed: {exc}",
                metadata={
                    "artifact_upload_completed": False,
                    "marker_write_completed": False,
                    "verification_required": True,
                    "exception_type": type(exc).__name__,
                },
            )
            return True
        if dispatch_result.continuation_started:
            logger.info(
                "v3 mark success via outbox: job_id=%s inventory_id=%s aisle_id=%s",
                p.job_id,
                p.aisle.inventory_id,
                p.aisle_id,
            )
            return False
        if dispatch_result.required_complete:
            try:
                tracker.record_artifacts_published(durable_artifacts=dispatch_result.durable_meta)
            except Exception as marker_e:
                p.exec_log.error(
                    "Artifacts",
                    f"Artifact marker write failed: {marker_e}",
                    payload={"error": str(marker_e)[:500]},
                )
                self._state.fail_finalization_and_aisle(
                    p.job_id,
                    p.aisle,
                    tracker=tracker,
                    error_code=FinalizationErrorCode.FINALIZATION_METADATA_WRITE_FAILED,
                    current_step=CurrentFinalizationStep.PUBLISH_ARTIFACTS,
                    message=f"Artifact marker write failed: {marker_e}",
                    metadata={
                        "artifact_upload_completed": True,
                        "marker_write_completed": False,
                        "verification_required": True,
                        "failed_marker": "ARTIFACTS_PUBLISHED",
                        "published_artifact_kinds": sorted(dispatch_result.durable_meta.keys()),
                        "exception_type": type(marker_e).__name__,
                    },
                )
                return True
            try:
                self._state.finalize_success(
                    p.job_id,
                    p.aisle,
                    p.report_path,
                    tracker=tracker,
                    run_metadata=p.result.run_metadata,
                    durable_artifacts=dispatch_result.durable_meta,
                )
            except Exception:
                return True
            return False
        published_required = {
            kind for kind in dispatch_result.published_kinds if is_required_artifact_kind(kind)
        }
        failed_required = {
            kind
            for kind in dispatch_result.permanently_failed_kinds
            if is_required_artifact_kind(kind)
        }
        if published_required and failed_required and not dispatch_result.required_complete:
            failed_kind = sorted(failed_required)[0]
            p.exec_log.error(
                "Artifacts",
                f"Partial durable artifact upload: {failed_kind}",
                payload={"failed_kind": failed_kind},
            )
            self._state.fail_finalization_and_aisle(
                p.job_id,
                p.aisle,
                tracker=tracker,
                error_code=FinalizationErrorCode.ARTIFACT_PUBLISH_PARTIAL,
                current_step=CurrentFinalizationStep.PUBLISH_ARTIFACTS,
                message=f"Durable artifact upload partial failure: {failed_kind}",
                metadata={
                    "failed_kind": failed_kind,
                    "published_artifacts": {
                        kind: dispatch_result.durable_meta[kind]
                        for kind in sorted(published_required)
                        if kind in dispatch_result.durable_meta
                    },
                },
            )
            return True
        if dispatch_result.permanently_failed_kinds:
            failed_entries = list(dispatch_result.failed_entries)
            if not failed_entries and self._artifact_outbox_store is not None:
                from src.application.services.artifact_publication_diagnostics import (
                    failed_outbox_entry_summary,
                )

                for kind in sorted(dispatch_result.permanently_failed_kinds):
                    entry = self._artifact_outbox_store.get_entry(p.job_id, kind)
                    if entry is not None:
                        failed_entries.append(failed_outbox_entry_summary(entry))
            logger.error(
                "artifact.publication.required_permanently_failed job_id=%s failed_kinds=%s failed_entries=%s",
                p.job_id,
                sorted(dispatch_result.permanently_failed_kinds),
                failed_entries,
            )
            p.exec_log.error(
                "Artifacts",
                "Required artifact publication permanently failed",
                payload={
                    "failed_kinds": sorted(dispatch_result.permanently_failed_kinds),
                    "failed_entries": failed_entries,
                },
            )
            self._state.fail_finalization_and_aisle(
                p.job_id,
                p.aisle,
                tracker=tracker,
                error_code=FinalizationErrorCode.ARTIFACT_PUBLISH_FAILED,
                current_step=CurrentFinalizationStep.PUBLISH_ARTIFACTS,
                message="Required artifact publication permanently failed",
                metadata={
                    "failed_kinds": sorted(dispatch_result.permanently_failed_kinds),
                    "failed_entries": failed_entries,
                    "published_artifact_kinds": sorted(dispatch_result.published_kinds),
                    "verification_required": True,
                },
            )
            return True
        if dispatch_result.retry_scheduled_kinds:
            p.exec_log.info(
                "Artifacts",
                "Durable artifact publication incomplete; autonomous retry scheduled",
                payload={
                    "retry_kinds": sorted(dispatch_result.retry_scheduled_kinds),
                    "published_kinds": sorted(dispatch_result.published_kinds),
                },
            )
            self._state.mark_artifact_publication_retry_pending(
                p.job_id,
                tracker=tracker,
                retry_kinds=dispatch_result.retry_scheduled_kinds,
                published_kinds=dispatch_result.published_kinds,
            )
            return False
        p.exec_log.error("Artifacts", "Required artifact publication produced no durable outputs")
        self._state.fail_finalization_and_aisle(
            p.job_id,
            p.aisle,
            tracker=tracker,
            error_code=FinalizationErrorCode.ARTIFACT_PUBLISH_FAILED,
            current_step=CurrentFinalizationStep.PUBLISH_ARTIFACTS,
            message="Required artifact publication produced no durable outputs",
        )
        return True

    def _v3_begin_run_monitoring(self, req: _V3RunMonitoringRequest) -> _V3WorkerRuntimeHandles:
        """Create run_dir logger, execution log, and cooperative heartbeat thread."""
        run_dir = req.base_path / req.job_id / RUN_ID
        log = setup_logger(str(req.job_dir), req.job_id, RUN_ID, console=False)
        exec_log = ExecutionLogWriter(run_dir)
        exec_log.structured_event(
            job_id=req.job_id,
            inventory_id=req.aisle.inventory_id,
            aisle_id=req.aisle_id,
            attempt=req.job.attempt_count,
            stage="WorkerLaunch",
            substep="startup_confirmation",
            event="job.spawn_succeeded",
            details={"execution_id": req.job.execution_id},
        )
        logger.info(
            "v3 execution log initialized: job_id=%s run_dir=%s",
            req.job_id,
            str(run_dir),
        )

        stop_heartbeat = threading.Event()
        cancel_event_emitted: dict[str, bool] = {
            "requested": False,
            "detected": False,
            "cancelled": False,
        }

        def heartbeat_loop() -> None:
            while not stop_heartbeat.wait(self._heartbeat_interval_sec):
                current_job = self._state.heartbeat(req.job_id)
                if current_job is None:
                    continue
                exec_log.structured_event(
                    job_id=req.job_id,
                    inventory_id=req.aisle.inventory_id,
                    aisle_id=req.aisle_id,
                    attempt=current_job.attempt_count,
                    stage=current_job.current_stage or "Pipeline",
                    substep=current_job.current_substep,
                    event="job.heartbeat",
                )

        heartbeat_thread = threading.Thread(
            target=heartbeat_loop, name=f"job-heartbeat-{req.job_id}", daemon=True
        )
        heartbeat_thread.start()
        return _V3WorkerRuntimeHandles(
            run_dir=run_dir,
            log=log,
            exec_log=exec_log,
            stop_heartbeat=stop_heartbeat,
            heartbeat_thread=heartbeat_thread,
            cancel_event_emitted=cancel_event_emitted,
        )

    def _v3_run_job_body(self, base_path: Path, job_id: str, prep: _V3PreparedJob) -> bool:
        """Dirs, pipeline input, hybrid run, persist, artifacts, success — matches pre-refactor order."""
        job = prep.job
        aisle = prep.aisle
        aisle_id = prep.aisle_id
        assets = prep.assets

        settings = load_settings()
        output_dir = Path(settings.output_dir)
        v3_base = output_dir / "v3_uploads"
        job_dir = base_path / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        logger.info(
            "v3 run dirs ready: job_id=%s output_dir=%s job_dir=%s v3_base=%s",
            job_id,
            str(output_dir),
            str(job_dir),
            str(v3_base),
        )

        resolved_in = self._v3_resolve_pipeline_inputs_or_abort(
            _V3PipelineInputRequest(
                job_id=job_id,
                aisle=aisle,
                aisle_id=aisle_id,
                assets=assets,
                v3_base=v3_base,
                job_dir=job_dir,
                settings=settings,
            )
        )
        if resolved_in is None:
            return True
        analysis_context, job_input, video_path = resolved_in

        rt = self._v3_begin_run_monitoring(
            _V3RunMonitoringRequest(
                base_path=base_path,
                job_id=job_id,
                job_dir=job_dir,
                job=job,
                aisle=aisle,
                aisle_id=aisle_id,
            )
        )

        def execution_observer(
            stage: str, substep: str | None, event: str, details: dict[str, Any] | None
        ) -> None:
            self._state.update_runtime_status(
                job_id,
                stage=stage,
                substep=substep,
            )

        def cancellation_checkpoint(stage: str, substep: str | None, reason: str) -> None:
            self._state.raise_if_cancellation_requested(
                job_id,
                exec_log=rt.exec_log,
                inventory_id=aisle.inventory_id,
                aisle_id=aisle_id,
                stage=stage,
                substep=substep,
                reason=reason,
                cancel_event_emitted=rt.cancel_event_emitted,
            )

        try:
            hybrid_out = self._v3_hybrid_run_and_load_report(
                _V3HybridRunParams(
                    base_path=base_path,
                    job_id=job_id,
                    job=job,
                    aisle=aisle,
                    aisle_id=aisle_id,
                    run_dir=rt.run_dir,
                    settings=settings,
                    log=rt.log,
                    pipeline_video_path=video_path or "",
                    job_input=job_input,
                    analysis_context=analysis_context,
                    execution_observer=execution_observer,
                    cancellation_checkpoint=cancellation_checkpoint,
                )
            )
            if hybrid_out is None:
                return True
            report, result, report_path = hybrid_out

            # Finalization order (intentional):
            # 1) PersistAisleResult — domain rows (positions, product_records, evidences, …).
            #    Does not set aisles.operational_job_id (that happens in mark_success for production).
            # 2) Durable artifact upload — execution log + reports to ArtifactStore.
            # 3) mark_success — job SUCCEEDED + result_json including durable_artifacts metadata;
            #    for production inventories, sets aisles.operational_job_id = job_id (review slice).
            #
            # If step (2) fails after step (1), the job and aisle are marked FAILED with a clear error.
            # Domain data from (1) may already be committed (partial finalization). There is no automatic
            # compensation; operators should treat FAILED as "processing did not fully complete" and use
            # a new or explicitly reset job if work must be redone. Re-running the same job id without
            # reset is out of band for this executor (claim path expects terminal FAILED to stay terminal).
            if self._v3_persist_durables_and_mark_success(
                _V3FinalizeAfterPipelineParams(
                    job_id=job_id,
                    aisle=aisle,
                    aisle_id=aisle_id,
                    run_dir=rt.run_dir,
                    exec_log=rt.exec_log,
                    result=result,
                    report_path=report_path,
                    report=report,
                    cancellation_checkpoint=cancellation_checkpoint,
                    cancel_event_emitted=rt.cancel_event_emitted,
                )
            ):
                return True
        except PipelineCancellationRequestedError as e:
            logger.info("v3 job %s cancellation detected cooperatively: %s", job_id, e)
            self._state.cancel_job_and_aisle(
                job_id,
                aisle,
                str(e),
                exec_log=rt.exec_log,
                cancel_event_emitted=rt.cancel_event_emitted,
            )
            return True
        except Exception as e:
            logger.exception("v3 job %s failed: %s", job_id, e)
            if rt.run_dir.is_dir():
                try:
                    err_log = ExecutionLogWriter(rt.run_dir)
                    err_log.error("Pipeline", f"Job failed: {e}", payload={"error": str(e)[:500]})
                except Exception:
                    pass
            self._state.fail_job_and_aisle(job_id, aisle, str(e))
            logger.info(
                "v3 mark failed: job_id=%s inventory_id=%s aisle_id=%s error=%s",
                job_id,
                aisle.inventory_id,
                aisle_id,
                str(e),
            )
        finally:
            rt.stop_heartbeat.set()
            rt.heartbeat_thread.join(timeout=1.0)

        return True
