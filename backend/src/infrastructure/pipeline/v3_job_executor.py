"""
V3 process_aisle job executor — Épica 6.

Thin orchestrator delegating to:
V3JobPreparationService, V3JobMonitoringService, V3CancellationCoordinator,
V3PipelineExecutionService, V3JobFinalizationService, V3WorkerFailureHandler.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
    ResultEvidenceRepository,
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
from src.application.services.operational_result_promotion_service import (
    OperationalResultPromotionService,
)
from src.application.services.supplier_prompt_resolver import SupplierPromptResolver
from src.application.services.supplier_reference_image_resolver import (
    SupplierReferenceImageResolver,
)
from src.application.services.traceability_artifact_service import TraceabilityArtifactService
from src.application.use_cases.pipeline.persist_aisle_result import (
    PersistAisleResultUseCase,
)
from src.application.use_cases.pipeline.recompute_consolidated_counts import (
    RecomputeConsolidatedCountsUseCase,
)
from src.config import Settings, load_settings
from src.domain.aisle.entities import Aisle
from src.infrastructure.pipeline.finalization_stage_recorder import FinalizationStageRecorder
from src.infrastructure.pipeline.hybrid_report_to_domain_adapter import (
    default_map_hybrid_report_to_domain,
)
from src.infrastructure.pipeline.v3_cancellation_coordinator import V3CancellationCoordinator
from src.infrastructure.pipeline.v3_execution_artifacts_service import V3ExecutionArtifactsService
from src.infrastructure.pipeline.v3_job_execution_state import V3JobExecutionStateService
from src.infrastructure.pipeline.v3_job_finalization_service import (
    V3JobFinalizationRequest,
    V3JobFinalizationService,
)
from src.infrastructure.pipeline.v3_job_monitoring_service import (
    V3JobMonitoringRequest,
    V3JobMonitoringService,
)
from src.infrastructure.pipeline.v3_job_preparation_service import (
    V3JobPreparationService,
    V3PreparedJob,
)
from src.infrastructure.pipeline.v3_pipeline_execution_service import (
    V3PipelineExecutionRequest,
    V3PipelineExecutionService,
)
from src.infrastructure.pipeline.v3_process_aisle_pipeline_runner import (
    V3ProcessAislePipelineRunner,
    visual_reference_failure_metadata,
)
from src.infrastructure.pipeline.v3_worker_failure_handler import (
    V3WorkerFailureHandler,
    V3WorkerFailureRequest,
)
from src.infrastructure.pipeline.worker_durable_artifact_publisher import (
    DEFAULT_V3_WORKER_RUN_SEGMENT,
)
from src.pipeline.contracts.analysis_context import AnalysisContext, analysis_context_from_dict
from src.pipeline.errors import PipelineCancellationRequestedError
from src.pipeline.run_metadata import RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT

logger = logging.getLogger(__name__)

# Pipeline/output directory segment under {base}/{job_id}/; must match DEFAULT_V3_WORKER_RUN_SEGMENT.
RUN_ID = DEFAULT_V3_WORKER_RUN_SEGMENT


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
class _GlobalFallbackRuntimeCtx:
    """Runtime dirs/observers needed to run GLOBAL_BATCH after the internal aisle pass."""

    base_path: Path
    v3_base: Path
    job_dir: Path
    run_dir: Path
    log: logging.Logger
    execution_observer: Any
    cancellation_checkpoint: Any
    legacy_local_read_enabled: bool = False


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
        result_evidence_repo: ResultEvidenceRepository | None = None,
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
        job_source_asset_repo=None,
    ) -> None:
        self._job_repo = job_repo
        self._aisle_repo = aisle_repo
        self._inventory_repo = inventory_repo
        self._source_asset_repo = source_asset_repo
        self._job_source_asset_repo = job_source_asset_repo
        self._artifact_store = artifact_store
        self._clock = clock
        self._position_repo = position_repo
        self._evidence_repo = evidence_repo
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
        self.__artifacts = V3ExecutionArtifactsService(artifact_store)
        supplier_resolver = SupplierReferenceImageResolver(supplier_reference_image_repo)
        context_builder = AisleAnalysisContextBuilder(supplier_resolver)
        self.__pipeline_runner = V3ProcessAislePipelineRunner(
            supplier_reference_image_repo=supplier_reference_image_repo,
            artifact_store=artifact_store,
            context_builder=context_builder,
        )
        self.__supplier_prompt_resolver: SupplierPromptResolver | None = None
        if client_supplier_repo is not None and supplier_prompt_config_repo is not None:
            self.__supplier_prompt_resolver = SupplierPromptResolver(
                inventory_repo=inventory_repo,
                aisle_repo=aisle_repo,
                client_supplier_repo=client_supplier_repo,
                supplier_prompt_config_repo=supplier_prompt_config_repo,
            )
        if (
            raw_label_repo is None
            or normalized_label_repo is None
            or final_count_repo is None
            or result_evidence_repo is None
            or aisle_repo is None
            or job_scoped_recompute_factory is None
            or job_result_uow_factory is None
        ):
            raise ValueError(
                "V3JobExecutor requires raw_label_repo, normalized_label_repo, "
                "final_count_repo, result_evidence_repo, aisle_repo, job_scoped_recompute_factory, "
                "and job_result_uow_factory for PersistAisleResultUseCase"
            )
        self.__persist_use_case = PersistAisleResultUseCase(
            position_repo=position_repo,
            product_record_repo=product_record_repo,
            evidence_repo=evidence_repo,
            result_evidence_repo=result_evidence_repo,
            clock=clock,
            hybrid_mapper=default_map_hybrid_report_to_domain,
            aisle_repo=aisle_repo,
            raw_label_repo=raw_label_repo,
            normalized_label_repo=normalized_label_repo,
            final_count_repo=final_count_repo,
            job_scoped_recompute_factory=job_scoped_recompute_factory,
            job_result_uow_factory=job_result_uow_factory,
        )
        self._result_evidence_repo = result_evidence_repo
        self._traceability_artifact_service = TraceabilityArtifactService(
            result_evidence_repo=result_evidence_repo,
            clock=clock,
        )
        _ = recompute_consolidated_uc
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
        self.__artifact_dispatcher: ArtifactPublicationDispatcher | None = None
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
        self._preparation_service = V3JobPreparationService(
            job_repo=job_repo,
            aisle_repo=aisle_repo,
            source_asset_repo=source_asset_repo,
            state_service=self._state,
            clock=clock,
        )
        self._monitoring_service = V3JobMonitoringService(
            state_service=self._state,
            startup_progress_timeout_sec=float(
                getattr(load_settings(), "job_startup_progress_timeout_seconds", 120.0)
            ),
        )
        self._cancellation_coordinator = V3CancellationCoordinator(state_service=self._state)
        self._pipeline_execution_service = V3PipelineExecutionService(
            state_service=self._state,
            pipeline_runner=self._pipeline_runner,
            supplier_prompt_resolver=self._supplier_prompt_resolver,
        )
        self._finalization_service = V3JobFinalizationService(
            job_repo=job_repo,
            clock=clock,
            state_service=self._state,
            persist_use_case=self._persist_use_case,
            artifacts_service=self._artifacts,
            traceability_artifact_service=self._traceability_artifact_service,
            artifact_dispatcher=self._artifact_dispatcher,
            artifact_manifest_store=artifact_manifest_store,
            artifact_outbox_store=artifact_publication_outbox_store,
            stage_recorder=self._stage_recorder,
        )
        self._failure_handler = V3WorkerFailureHandler(state_service=self._state)

    @property
    def _artifact_dispatcher(self) -> ArtifactPublicationDispatcher | None:
        return self.__artifact_dispatcher

    @_artifact_dispatcher.setter
    def _artifact_dispatcher(self, dispatcher: ArtifactPublicationDispatcher | None) -> None:
        # Compatibility bridge for tests/callers that override executor._artifact_dispatcher.
        # Keep the extracted finalization service in sync until collaborators are injected directly.
        self.__artifact_dispatcher = dispatcher
        if hasattr(self, "_finalization_service"):
            self._finalization_service._artifact_dispatcher = dispatcher

    @property
    def _pipeline_runner(self) -> V3ProcessAislePipelineRunner:
        # Compatibility bridge for tests/callers that override executor._pipeline_runner.
        # Keep the extracted pipeline execution service in sync until collaborators are injected directly.
        return self.__pipeline_runner

    @_pipeline_runner.setter
    def _pipeline_runner(self, runner: V3ProcessAislePipelineRunner) -> None:
        self.__pipeline_runner = runner
        if hasattr(self, "_pipeline_execution_service"):
            self._pipeline_execution_service._pipeline_runner = runner

    @property
    def _supplier_prompt_resolver(self) -> SupplierPromptResolver | None:
        return self.__supplier_prompt_resolver

    @_supplier_prompt_resolver.setter
    def _supplier_prompt_resolver(self, resolver: SupplierPromptResolver | None) -> None:
        # Compatibility bridge for tests/callers that override executor._supplier_prompt_resolver.
        self.__supplier_prompt_resolver = resolver
        if hasattr(self, "_pipeline_execution_service"):
            self._pipeline_execution_service._supplier_prompt_resolver = resolver

    @property
    def _artifacts(self) -> V3ExecutionArtifactsService:
        return self.__artifacts

    @_artifacts.setter
    def _artifacts(self, artifacts_service: V3ExecutionArtifactsService) -> None:
        # Compatibility bridge for tests/callers that override executor._artifacts.
        # Keep the extracted finalization service in sync until collaborators are injected directly.
        self.__artifacts = artifacts_service
        if hasattr(self, "_finalization_service"):
            self._finalization_service._artifacts = artifacts_service

    @property
    def _persist_use_case(self) -> PersistAisleResultUseCase:
        return self.__persist_use_case

    @_persist_use_case.setter
    def _persist_use_case(self, persist_use_case: PersistAisleResultUseCase) -> None:
        # Compatibility bridge for tests/callers that override executor._persist_use_case.
        # Keep the extracted finalization service in sync until collaborators are injected directly.
        self.__persist_use_case = persist_use_case
        if hasattr(self, "_finalization_service"):
            self._finalization_service._persist_use_case = persist_use_case

    def execute(self, base_path: Path, job_id: str) -> bool:
        """
        If job_id is a v3 process_aisle job: load aisle/assets, run pipeline, persist, update status; return True.
        Otherwise return False (caller may run legacy flow).
        """
        preparation = self._preparation_service.prepare(job_id)
        if preparation.stop:
            return preparation.return_value
        if preparation.prepared is None:
            logger.error(
                "V3 preparation returned continue without prepared job: job_id=%s",
                job_id,
            )
            return True
        return self._v3_run_job_body(base_path, job_id, preparation.prepared)

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

    def _run_global_external_fallback_after_internal(
        self,
        *,
        job: Any,
        aisle: Aisle,
        assets: list[Any],
        settings: Settings,
        is_cancelled: Any,
        event_publisher: Any,
        state_repo: Any,
        lease_repo: Any,
        ctx: _GlobalFallbackRuntimeCtx,
    ) -> bool:
        """Run GLOBAL_BATCH after internal aisle pass. False => caller must stop (failed)."""
        import uuid as _uuid

        from src.application.services.image_processing.external_fallback_mode import (
            EXTERNAL_FALLBACK_MODE_GLOBAL_BATCH,
        )
        from src.application.services.image_processing.external_provider_fallback_orchestrator import (
            ExternalFallbackSnapshot,
        )
        from src.application.services.image_processing.global_external_fallback_coordinator import (
            GlobalExternalFallbackCoordinator,
        )
        from src.application.services.image_processing.global_fallback_merge_policy import (
            InternalAssetEvidence,
        )
        from src.infrastructure.pipeline.global_fallback_hybrid_runner import (
            HybridGlobalFallbackBatchAnalyzer,
        )
        from src.infrastructure.pipeline.v3_image_processing_bridge import (
            build_default_code_scan_persister,
        )
        from src.pipeline.stages.frame_acquisition_stage import HYBRID_MAX_FRAMES_LOAD_CAP
        from src.runtime.app_container import get_app_container

        params = job.engine_params_json if isinstance(job.engine_params_json, dict) else {}
        ident = params.get("identification_execution")
        snapshot = ExternalFallbackSnapshot.from_identification_execution(
            ident if isinstance(ident, dict) else None
        )
        if snapshot is None or not snapshot.enabled:
            return True
        if snapshot.fallback_mode != EXTERNAL_FALLBACK_MODE_GLOBAL_BATCH:
            return True
        if lease_repo is None:
            logger.error(
                "global_fallback.lease_repo_unavailable job_id=%s",
                job.id,
            )
            self._state.fail_job_and_aisle(
                job.id,
                aisle,
                "GLOBAL_BATCH requires job processing lease repository",
                failure_code="GLOBAL_FALLBACK_LEASE_UNAVAILABLE",
            )
            return False

        container = get_app_container()
        persister = build_default_code_scan_persister(
            job_source_asset_repo=container.get_job_source_asset_repo(),
            source_asset_repo=self._source_asset_repo,
            clock=self._clock,
            unit_of_work_factory=container.get_manual_image_result_uow_factory(),
        )

        def _load_internal(job_id: str, asset_id: str) -> InternalAssetEvidence | None:
            status = None
            code = None
            qty = None
            resolved = False
            if state_repo is not None:
                st = state_repo.get_by_job_and_asset(job_id, asset_id)
                if st is not None:
                    status = st.status.value if st.status is not None else None
                    last = (st.last_strategy or "").upper()
                    resolved = status == "RESOLVED" and last in (
                        "CODE_SCAN",
                        "INTERNAL_OCR",
                        "CODE_SCAN_PROCESSING",
                    )
            try:
                positions = self._position_repo.list_by_aisle(aisle.id, job_id=job_id)
            except TypeError:
                positions = self._position_repo.list_by_aisle(aisle.id)
            except Exception:
                positions = []
            for pos in positions or []:
                if getattr(pos, "job_id", None) and str(pos.job_id) != str(job_id):
                    continue
                summary = getattr(pos, "detected_summary_json", None) or {}
                if not isinstance(summary, dict):
                    continue
                src = summary.get("source_asset_id") or summary.get("source_image_id")
                if str(src or "") != asset_id:
                    continue
                code = summary.get("internal_code")
                try:
                    products = self._product_record_repo.list_by_position(pos.id)
                    if products:
                        qty = getattr(products[0], "detected_quantity", None)
                except Exception:
                    qty = None
                if code and qty is not None:
                    resolved = True
                break
            return InternalAssetEvidence(
                asset_id=asset_id,
                status=status,
                internal_code=str(code).strip() if code else None,
                quantity=float(qty) if isinstance(qty, (int, float)) else None,
                resolved_internal=bool(resolved and code and qty is not None),
            )

        def _filename_map(asset_list: Any) -> dict[str, str]:
            out: dict[str, str] = {}
            for a in asset_list:
                aid = getattr(a, "id", None)
                if not aid:
                    continue
                for key in (
                    getattr(a, "original_filename", None),
                    getattr(a, "filename", None),
                    getattr(a, "storage_key", None),
                ):
                    if key and str(key).strip():
                        out[str(key).strip()] = str(aid)
            return out

        analyzer = HybridGlobalFallbackBatchAnalyzer(
            pipeline_execution_service=self._pipeline_execution_service,
            pipeline_runner=self._pipeline_runner,
            settings=settings,
            base_path=ctx.base_path,
            v3_base=ctx.v3_base,
            job_dir=ctx.job_dir,
            run_dir=ctx.run_dir,
            inventory_repo=self._inventory_repo,
            log=ctx.log,
            execution_observer=ctx.execution_observer,
            cancellation_checkpoint=ctx.cancellation_checkpoint,
            legacy_local_read_enabled=ctx.legacy_local_read_enabled,
        )
        max_frames = int(
            getattr(settings, "hybrid_max_frames", None) or HYBRID_MAX_FRAMES_LOAD_CAP
        )
        max_frames = min(max_frames, HYBRID_MAX_FRAMES_LOAD_CAP)

        coordinator = GlobalExternalFallbackCoordinator(
            lease_repo=lease_repo,
            clock=self._clock,
            batch_analyzer=analyzer,
            result_persister=persister,
            event_publisher=event_publisher,
            state_repo=state_repo,
            lease_duration_seconds=int(
                getattr(settings, "image_processing_batch_lease_seconds", 600) or 600
            ),
            max_frames_per_batch=max_frames,
            load_internal_evidence=_load_internal,
            filename_to_asset_id=_filename_map,
        )
        fresh_job = self._job_repo.get_by_id(job.id) or job
        outcome = coordinator.process_after_internal_pass(
            job=fresh_job,
            aisle=aisle,
            assets=assets,
            snapshot=snapshot,
            worker_token=str(_uuid.uuid4()),
            is_cancelled=is_cancelled,
            configuration_fingerprint=str(
                getattr(job, "configuration_snapshot_version", "") or ""
            ),
            execution_id=str(job.id),
        )
        if outcome.public_summary:
            self._job_repo.merge_result_json(
                job.id, {"global_fallback": outcome.public_summary}
            )
        if outcome.cancelled:
            return True
        if outcome.failed:
            self._state.fail_job_and_aisle(
                job.id,
                aisle,
                outcome.error_message or "GLOBAL_BATCH fallback failed",
                failure_code=outcome.error_code or "FALLBACK_BATCH_FAILED",
            )
            return False
        return True

    def _run_code_scan_path(
        self,
        *,
        job: Any,
        aisle: Aisle,
        aisle_id: str,
        assets: list[Any],
        settings: Settings,
        exec_log: Any,
        cancel_event_emitted: dict[str, bool],
        runtime_abort_event: Any = None,
        global_fallback_ctx: _GlobalFallbackRuntimeCtx | None = None,
    ) -> bool:
        """Phase 3 CODE_SCAN execution — deterministic per-image scan, no LLM pipeline."""
        import uuid as _uuid

        from src.application.errors import (
            CodeScanPipelineMisconfiguredError,
            ImageProcessingRepositoryUnavailableError,
        )
        from src.application.services.image_processing.code_scan_job_outcome_policy import (
            CodeScanJobOutcome,
        )
        from src.domain.jobs.entities import JobStatus
        from src.infrastructure.pipeline.v3_image_processing_bridge import (
            build_default_code_scan_orchestrator,
            build_default_code_scan_persister,
            build_default_code_scan_strategy,
            build_default_external_fallback_orchestrator,
            progress_to_public_dict,
            run_orchestrated_code_scan,
        )
        from src.runtime.app_container import get_app_container

        job_id = job.id
        container = get_app_container()
        require_sql = container.is_sql_repository_backend()
        try:
            state_repo = container.get_job_asset_processing_state_repo()
            attempt_repo = container.get_processing_attempt_repo()
            lease_repo = container.get_job_processing_lease_repo()
            batch_attempt_repo = container.get_batch_processing_attempt_repo()
        except Exception as repo_exc:
            logger.error(
                "code_scan.repo_resolve_failed job_id=%s require_sql=%s",
                job_id,
                require_sql,
                exc_info=True,
            )
            if require_sql:
                self._state.fail_job_and_aisle(
                    job_id,
                    aisle,
                    f"Phase 3 SQL image-processing repositories unavailable: {repo_exc}",
                    failure_code="IMAGE_PROCESSING_REPOSITORY_UNAVAILABLE",
                )
                return True
            state_repo = attempt_repo = lease_repo = batch_attempt_repo = None

        event_publisher = None
        try:
            from src.application.services.image_processing.processing_event_publisher import (
                CompositeProcessingEventPublisher,
                ExecutionLogProcessingEventPublisher,
                RepositoryProcessingEventPublisher,
            )

            exec_log_publisher = ExecutionLogProcessingEventPublisher(
                exec_log=exec_log,
                inventory_id=aisle.inventory_id,
                aisle_id=aisle_id,
                attempt=int(getattr(job, "attempt_count", 1) or 1),
                stage="CodeScan",
            )
            repo_publisher = None
            if bool(getattr(settings, "processing_events_persistence_enabled", False)):
                try:
                    repo_publisher = RepositoryProcessingEventPublisher(
                        event_repo=container.get_processing_event_repo(),
                        clock=container.get_clock(),
                    )
                except Exception as pub_exc:
                    logger.warning(
                        "code_scan.event_publisher_unavailable job_id=%s err=%s",
                        job_id,
                        pub_exc,
                    )
            event_publisher = CompositeProcessingEventPublisher(
                *(p for p in (repo_publisher, exec_log_publisher) if p is not None)
            )

            def _publish_job_event(
                event_type: str,
                *,
                message: str | None = None,
                error_code: str | None = None,
                metadata: dict | None = None,
                severity: str = "INFO",
            ) -> None:
                try:
                    event_publisher.publish(
                        job_id=job_id,
                        event_type=event_type,
                        strategy="CODE_SCAN",
                        severity=severity,
                        message=message,
                        error_code=error_code,
                        metadata=metadata,
                    )
                except Exception:
                    logger.debug(
                        "code_scan.job_event_publish_skipped job_id=%s event=%s",
                        job_id,
                        event_type,
                        exc_info=True,
                    )

            strategy = build_default_code_scan_strategy(
                settings, self._artifact_store, event_publisher=event_publisher
            )
            persister = build_default_code_scan_persister(
                job_source_asset_repo=container.get_job_source_asset_repo(),
                source_asset_repo=self._source_asset_repo,
                clock=self._clock,
                unit_of_work_factory=container.get_manual_image_result_uow_factory(),
            )

            def _is_cancelled() -> bool:
                if runtime_abort_event is not None and runtime_abort_event.is_set():
                    return True
                current = self._job_repo.get_by_id(job_id)
                if current is None:
                    return True
                if current.status in (
                    JobStatus.FAILED,
                    JobStatus.CANCELED,
                    JobStatus.SUCCEEDED,
                ):
                    return True
                return current.status == JobStatus.CANCEL_REQUESTED

            if _is_cancelled():
                logger.warning("code_scan.aborted_before_orchestrator job_id=%s", job_id)
                return True

            external_fallback = None
            external_request_repo = None
            if attempt_repo is not None:
                try:
                    external_request_repo = container.get_external_image_analysis_request_repo()
                except Exception:
                    external_request_repo = None
                external_fallback = build_default_external_fallback_orchestrator(
                    settings=settings,
                    artifact_store=self._artifact_store,
                    attempt_repo=attempt_repo,
                    clock=self._clock,
                    is_cancelled=_is_cancelled,
                    request_repo=external_request_repo,
                    event_publisher=event_publisher,
                )

            orch = build_default_code_scan_orchestrator(
                self._clock,
                attempts_enabled=bool(settings.processing_attempts_enabled),
                state_repo=state_repo,
                attempt_repo=attempt_repo,
                lease_repo=lease_repo,
                batch_attempt_repo=batch_attempt_repo,
                result_evidence_repo=self._result_evidence_repo,
                evidence_repo=self._evidence_repo,
                position_repo=self._position_repo,
                code_scan_strategy=strategy,
                result_persister=persister,
                code_scan_concurrency=int(settings.max_image_processing_concurrency),
                require_sql=require_sql,
                abandoned_processing_ttl_seconds=(settings.image_processing_abandoned_ttl_seconds),
                manual_coverage_repo=container.get_manual_image_coverage_repo(),
                external_fallback=external_fallback,
            )
        except ImageProcessingRepositoryUnavailableError as unavailable:
            logger.error("code_scan.repos_unavailable job_id=%s err=%s", job_id, unavailable)
            self._state.fail_job_and_aisle(
                job_id,
                aisle,
                str(unavailable),
                failure_code="IMAGE_PROCESSING_REPOSITORY_UNAVAILABLE",
            )
            return True
        except Exception as build_exc:
            # Fail closed before the asset loop — never leave heartbeat-only RUNNING.
            logger.exception("code_scan.startup_failed job_id=%s", job_id)
            if event_publisher is not None:
                try:
                    event_publisher.publish(
                        job_id=job_id,
                        event_type="job.failed",
                        strategy="CODE_SCAN",
                        severity="ERROR",
                        message="CODE_SCAN startup failed before processing_started",
                        error_code="CODE_SCAN_STARTUP_FAILED",
                        metadata={"error_type": type(build_exc).__name__},
                    )
                except Exception:
                    pass
            self._state.fail_job_and_aisle(
                job_id,
                aisle,
                f"CODE_SCAN startup failed: {type(build_exc).__name__}",
                failure_code="CODE_SCAN_STARTUP_FAILED",
            )
            return True

        def _merge_progress(progress) -> None:
            public = progress_to_public_dict(progress)
            self._job_repo.merge_result_json(job_id, {"asset_progress": public})
            # Heartbeat alone is not progress — advance runtime stage from asset counts.
            processed = (
                int(public.get("resolved", 0) or 0)
                + int(public.get("failed", 0) or 0)
                + int(public.get("manual_review", 0) or 0)
                + int(public.get("unrecognized", 0) or 0)
            )
            self._state.update_runtime_status(
                job_id,
                stage="CodeScan",
                substep=f"assets_processed:{processed}/{public.get('total', len(assets))}",
            )

        total_assets = len(assets)
        if _is_cancelled():
            logger.warning("code_scan.aborted_before_processing_started job_id=%s", job_id)
            return True
        self._state.update_runtime_status(job_id, stage="CodeScan", substep="processing_started")
        _publish_job_event(
            "job.processing_started",
            message="CODE_SCAN processing started",
            metadata={"total_assets": total_assets},
        )
        _publish_job_event(
            "code_scan.processing_started",
            message="CODE_SCAN strategy entered",
            metadata={"total_assets": total_assets},
        )
        _publish_job_event(
            "job.assets_loaded",
            message="job source assets ready for CODE_SCAN",
            metadata={
                "total_assets": total_assets,
                "assets_eligible": total_assets,
                "assets_skipped": 0,
            },
        )
        _publish_job_event(
            "job.asset_loop_started",
            message="per-asset CODE_SCAN loop started",
            metadata={"total_assets": total_assets},
        )

        try:
            outcome = run_orchestrated_code_scan(
                orchestrator=orch,
                job=job,
                aisle=aisle,
                assets=assets,
                pipeline_enabled=bool(settings.aisle_identification_pipeline_enabled),
                orchestrator_enabled=bool(settings.image_processing_orchestrator_enabled),
                code_scan_processing_enabled=True,
                is_cancelled=_is_cancelled,
                worker_token=str(_uuid.uuid4()),
                merge_progress=_merge_progress,
            )
        except CodeScanPipelineMisconfiguredError as misconfig:
            logger.error("code_scan.misconfigured job_id=%s err=%s", job_id, misconfig)
            _publish_job_event(
                "job.failed",
                message=str(misconfig)[:500],
                error_code="CODE_SCAN_PIPELINE_MISCONFIGURED",
                severity="ERROR",
            )
            self._state.fail_job_and_aisle(
                job_id,
                aisle,
                str(misconfig),
                failure_code="CODE_SCAN_PIPELINE_MISCONFIGURED",
            )
            return True
        except Exception as unhandled:
            logger.exception("code_scan.unhandled_worker_error job_id=%s", job_id)
            _publish_job_event(
                "job.failed",
                message=type(unhandled).__name__,
                error_code="UNHANDLED_WORKER_ERROR",
                severity="ERROR",
                metadata={"error_type": type(unhandled).__name__},
            )
            self._state.fail_job_and_aisle(
                job_id,
                aisle,
                f"CODE_SCAN unhandled error: {type(unhandled).__name__}",
                failure_code="UNHANDLED_WORKER_ERROR",
            )
            return True

        merge_payload: dict = {"asset_progress": progress_to_public_dict(outcome.progress)}
        if external_fallback is not None:
            from src.application.services.image_processing.external_provider_fallback_orchestrator import (
                resolve_fallback_progress_payload,
            )

            merge_payload.update(
                resolve_fallback_progress_payload(
                    job_id=job_id,
                    external_fallback=external_fallback,
                    external_request_repo=external_request_repo,
                    resolved_internal=int(getattr(outcome.progress, "resolved", 0) or 0),
                )
            )
        self._job_repo.merge_result_json(job_id, merge_payload)

        job_outcome = outcome.job_outcome
        assets_eligible = int(getattr(outcome, "assets_eligible", 0) or 0)
        assets_started = int(getattr(outcome, "assets_started", 0) or 0)
        progress_public = progress_to_public_dict(outcome.progress)
        code_scan_counters = {
            "total_assets": total_assets,
            "assets_eligible": assets_eligible,
            "assets_started": assets_started,
            "assets_resolved": int(progress_public.get("resolved", 0) or 0),
            "assets_manual_review": int(progress_public.get("manual_review", 0) or 0),
            "assets_unrecognized": int(progress_public.get("unrecognized", 0) or 0),
            "assets_failed_technical": int(progress_public.get("failed", 0) or 0),
            "assets_skipped": max(0, total_assets - assets_eligible),
        }
        self._job_repo.merge_result_json(job_id, {"code_scan_counters": code_scan_counters})

        # Loop-not-executed is decided solely by AisleProcessingOrchestrator
        # (job_outcome FAILED + error_message CODE_SCAN_ASSET_LOOP_NOT_EXECUTED).

        if job_outcome is CodeScanJobOutcome.CANCELLED:
            current = self._job_repo.get_by_id(job_id)
            if current is not None and current.status == JobStatus.RUNNING:
                return self._cancellation_coordinator.handle_pipeline_cancellation(
                    job_id=job_id,
                    aisle=aisle,
                    error=PipelineCancellationRequestedError(outcome.error_message or "cancelled"),
                    exec_log=exec_log,
                    cancel_event_emitted=cancel_event_emitted,
                )
            return True

        if job_outcome is CodeScanJobOutcome.FAILED:
            current = self._job_repo.get_by_id(job_id)
            if current is not None and current.status == JobStatus.RUNNING:
                failure_code = (
                    "CODE_SCAN_ASSET_LOOP_NOT_EXECUTED"
                    if (outcome.error_message or "") == "CODE_SCAN_ASSET_LOOP_NOT_EXECUTED"
                    else "CODE_SCAN_FAILED"
                )
                _publish_job_event(
                    "job.failed",
                    message=(outcome.error_message or "code_scan_failed")[:500],
                    error_code=failure_code,
                    severity="ERROR",
                    metadata=code_scan_counters,
                )
                self._state.fail_job_and_aisle(
                    job_id,
                    aisle,
                    outcome.error_message or "code_scan_failed",
                    failure_code=failure_code,
                )
            return True

        # SUCCEEDED or PARTIALLY_COMPLETED — both are completed jobs. A partial run recorded
        # a mix of asset outcomes (some FAILED_TECHNICAL, some resolved/unrecognized/manual);
        # it is still a completed job, annotated in result_json for auditability.
        self._job_repo.merge_result_json(job_id, {"code_scan_outcome": job_outcome.value})
        if job_outcome is CodeScanJobOutcome.PARTIALLY_COMPLETED:
            self._job_repo.merge_result_json(job_id, {"code_scan_partial": True})

        if global_fallback_ctx is not None:
            gf = self._run_global_external_fallback_after_internal(
                job=job,
                aisle=aisle,
                assets=assets,
                settings=settings,
                is_cancelled=_is_cancelled,
                event_publisher=event_publisher,
                state_repo=state_repo,
                lease_repo=lease_repo,
                ctx=global_fallback_ctx,
            )
            if gf is False:
                return True

        _publish_job_event(
            "job.finalization_started",
            message="CODE_SCAN finalization started",
            metadata={"outcome": job_outcome.value, **code_scan_counters},
        )
        if _is_cancelled():
            logger.warning("code_scan.aborted_before_success_finalization job_id=%s", job_id)
            return True
        try:
            self._state.finalize_code_scan_success(job_id, aisle)
            _publish_job_event(
                "job.completed",
                message="CODE_SCAN job completed",
                metadata={
                    "outcome": job_outcome.value,
                    "asset_progress": progress_to_public_dict(outcome.progress),
                    **code_scan_counters,
                },
            )
        except Exception as exc:
            logger.exception("code_scan.finalize_failed job_id=%s", job_id)
            _publish_job_event(
                "job.failed",
                message=f"code_scan finalization failed: {type(exc).__name__}",
                error_code="CODE_SCAN_FINALIZATION_FAILED",
                severity="ERROR",
            )
            self._state.fail_job_and_aisle(
                job_id,
                aisle,
                f"code_scan finalization failed: {exc}",
                failure_code="CODE_SCAN_FINALIZATION_FAILED",
            )
        return True

    def _run_internal_ocr_path(
        self,
        *,
        job: Any,
        aisle: Aisle,
        aisle_id: str,
        assets: list[Any],
        settings: Settings,
        exec_log: Any,
        cancel_event_emitted: dict[str, bool],
        runtime_abort_event: Any = None,
        global_fallback_ctx: _GlobalFallbackRuntimeCtx | None = None,
    ) -> bool:
        """Phase 4 INTERNAL_OCR execution — local Tesseract OCR per image, no LLM."""
        import uuid as _uuid

        from src.application.errors import (
            CodeScanPipelineMisconfiguredError,
            ImageProcessingRepositoryUnavailableError,
        )
        from src.application.services.image_processing.code_scan_job_outcome_policy import (
            CodeScanJobOutcome,
        )
        from src.domain.jobs.entities import JobStatus
        from src.infrastructure.pipeline.v3_image_processing_bridge import (
            build_default_code_scan_persister,
            build_default_external_fallback_orchestrator,
            build_default_internal_ocr_orchestrator,
            build_default_internal_ocr_strategy,
            progress_to_public_dict,
            run_orchestrated_internal_ocr,
        )
        from src.runtime.app_container import get_app_container

        job_id = job.id
        container = get_app_container()
        require_sql = container.is_sql_repository_backend()
        try:
            state_repo = container.get_job_asset_processing_state_repo()
            attempt_repo = container.get_processing_attempt_repo()
            lease_repo = container.get_job_processing_lease_repo()
            batch_attempt_repo = container.get_batch_processing_attempt_repo()
        except Exception as repo_exc:
            logger.error(
                "internal_ocr.repo_resolve_failed job_id=%s require_sql=%s",
                job_id,
                require_sql,
                exc_info=True,
            )
            if require_sql:
                exec_log.structured_event(
                    job_id=job_id,
                    inventory_id=aisle.inventory_id,
                    aisle_id=aisle_id,
                    attempt=job.attempt_count,
                    stage="InternalOcr",
                    substep="repo_resolve",
                    event="job.failed",
                    details={
                        "error_code": "IMAGE_PROCESSING_REPOSITORY_UNAVAILABLE",
                        "message": str(repo_exc)[:500],
                    },
                    level="error",
                )
                self._state.fail_job_and_aisle(
                    job_id,
                    aisle,
                    f"Phase 4 SQL image-processing repositories unavailable: {repo_exc}",
                    failure_code="IMAGE_PROCESSING_REPOSITORY_UNAVAILABLE",
                )
                return True
            state_repo = attempt_repo = lease_repo = batch_attempt_repo = None

        engine_params = job.engine_params_json if isinstance(job.engine_params_json, dict) else {}
        identification_execution = engine_params.get("identification_execution") or {}
        job_ocr_config = identification_execution.get("ocr_config")
        job_client_id = engine_params.get("client_id") or getattr(aisle, "client_id", None)

        from src.application.services.image_processing.processing_event_publisher import (
            CompositeProcessingEventPublisher,
            ExecutionLogProcessingEventPublisher,
            RepositoryProcessingEventPublisher,
        )

        exec_log_publisher = ExecutionLogProcessingEventPublisher(
            exec_log=exec_log,
            inventory_id=aisle.inventory_id,
            aisle_id=aisle_id,
            attempt=int(getattr(job, "attempt_count", 1) or 1),
            stage="InternalOcr",
        )
        repo_publisher = None
        if bool(getattr(settings, "processing_events_persistence_enabled", False)):
            try:
                repo_publisher = RepositoryProcessingEventPublisher(
                    event_repo=container.get_processing_event_repo(),
                    clock=container.get_clock(),
                )
            except Exception as pub_exc:
                logger.warning(
                    "internal_ocr.event_publisher_unavailable job_id=%s err=%s",
                    job_id,
                    pub_exc,
                )
        event_publisher = CompositeProcessingEventPublisher(
            *(p for p in (repo_publisher, exec_log_publisher) if p is not None)
        )

        def _publish_job_event(
            event_type: str,
            *,
            message: str | None = None,
            error_code: str | None = None,
            metadata: dict | None = None,
            severity: str = "INFO",
        ) -> None:
            try:
                event_publisher.publish(
                    job_id=job_id,
                    event_type=event_type,
                    strategy="INTERNAL_OCR",
                    severity=severity,
                    message=message,
                    error_code=error_code,
                    metadata=metadata,
                )
            except Exception:
                logger.debug(
                    "internal_ocr.job_event_publish_skipped job_id=%s event=%s",
                    job_id,
                    event_type,
                    exc_info=True,
                )

        try:
            strategy = build_default_internal_ocr_strategy(
                settings,
                self._artifact_store,
                client_id=job_client_id,
                ocr_config_override=job_ocr_config if isinstance(job_ocr_config, dict) else None,
                event_publisher=event_publisher,
            )
            persister = build_default_code_scan_persister(
                job_source_asset_repo=container.get_job_source_asset_repo(),
                source_asset_repo=self._source_asset_repo,
                clock=self._clock,
                unit_of_work_factory=container.get_manual_image_result_uow_factory(),
            )

            def _is_cancelled() -> bool:
                if runtime_abort_event is not None and runtime_abort_event.is_set():
                    return True
                current = self._job_repo.get_by_id(job_id)
                if current is None:
                    return True
                if current.status in (
                    JobStatus.FAILED,
                    JobStatus.CANCELED,
                    JobStatus.SUCCEEDED,
                ):
                    return True
                return current.status == JobStatus.CANCEL_REQUESTED

            external_fallback = None
            external_request_repo = None
            if attempt_repo is not None:
                try:
                    external_request_repo = container.get_external_image_analysis_request_repo()
                except Exception:
                    external_request_repo = None
                external_fallback = build_default_external_fallback_orchestrator(
                    settings=settings,
                    artifact_store=self._artifact_store,
                    attempt_repo=attempt_repo,
                    clock=self._clock,
                    is_cancelled=_is_cancelled,
                    request_repo=external_request_repo,
                    event_publisher=event_publisher,
                )

            orch = build_default_internal_ocr_orchestrator(
                self._clock,
                attempts_enabled=bool(settings.processing_attempts_enabled),
                state_repo=state_repo,
                attempt_repo=attempt_repo,
                lease_repo=lease_repo,
                batch_attempt_repo=batch_attempt_repo,
                result_evidence_repo=self._result_evidence_repo,
                evidence_repo=self._evidence_repo,
                position_repo=self._position_repo,
                internal_ocr_strategy=strategy,
                result_persister=persister,
                internal_ocr_concurrency=int(
                    getattr(settings, "max_internal_image_processing_concurrency", 1)
                ),
                require_sql=require_sql,
                abandoned_processing_ttl_seconds=(settings.image_processing_abandoned_ttl_seconds),
                manual_coverage_repo=container.get_manual_image_coverage_repo(),
                external_fallback=external_fallback,
            )
        except ImageProcessingRepositoryUnavailableError as unavailable:
            logger.error("internal_ocr.repos_unavailable job_id=%s err=%s", job_id, unavailable)
            _publish_job_event(
                "job.failed",
                message=str(unavailable)[:500],
                error_code="IMAGE_PROCESSING_REPOSITORY_UNAVAILABLE",
                severity="ERROR",
            )
            self._state.fail_job_and_aisle(
                job_id,
                aisle,
                str(unavailable),
                failure_code="IMAGE_PROCESSING_REPOSITORY_UNAVAILABLE",
            )
            return True

        self._job_repo.merge_result_json(
            job_id,
            {
                "internal_ocr_config": {
                    "engine": getattr(settings, "internal_ocr_engine", "tesseract"),
                    "language": getattr(settings, "internal_ocr_language", "spa+eng"),
                    "max_variants": getattr(settings, "internal_ocr_max_variants", 3),
                    "timeout_seconds": getattr(settings, "internal_ocr_timeout_seconds", 20),
                    "max_image_dimension": getattr(
                        settings, "internal_ocr_max_image_dimension", 2048
                    ),
                    "prefer_ean_as_internal_code": getattr(
                        settings, "internal_ocr_prefer_ean_as_internal_code", True
                    ),
                    "processor_version": "1.0.0",
                    "snapshot_version": getattr(job, "configuration_snapshot_version", None),
                }
            },
        )

        total_assets = len(assets)

        def _merge_progress(progress) -> None:
            public = progress_to_public_dict(progress)
            self._job_repo.merge_result_json(job_id, {"asset_progress": public})
            processed = (
                int(public.get("resolved", 0) or 0)
                + int(public.get("failed", 0) or 0)
                + int(public.get("manual_review", 0) or 0)
                + int(public.get("unrecognized", 0) or 0)
            )
            self._state.update_runtime_status(
                job_id,
                stage="InternalOcr",
                substep=f"assets_processed:{processed}/{public.get('total', total_assets)}",
            )

        self._state.update_runtime_status(job_id, stage="InternalOcr", substep="processing_started")
        if _is_cancelled():
            logger.warning("internal_ocr.aborted_before_processing_started job_id=%s", job_id)
            return True
        _publish_job_event(
            "job.processing_started",
            message="INTERNAL_OCR processing started",
            metadata={"total_assets": total_assets},
        )
        _publish_job_event(
            "job.assets_loaded",
            message="job source assets ready for INTERNAL_OCR",
            metadata={
                "total_assets": total_assets,
                "assets_eligible": total_assets,
                "assets_skipped": 0,
            },
        )
        _publish_job_event(
            "job.asset_loop_started",
            message="per-asset INTERNAL_OCR loop started",
            metadata={"total_assets": total_assets},
        )

        try:
            outcome = run_orchestrated_internal_ocr(
                orchestrator=orch,
                job=job,
                aisle=aisle,
                assets=assets,
                pipeline_enabled=bool(settings.aisle_identification_pipeline_enabled),
                orchestrator_enabled=bool(settings.image_processing_orchestrator_enabled),
                internal_ocr_processing_enabled=True,
                is_cancelled=_is_cancelled,
                worker_token=str(_uuid.uuid4()),
                merge_progress=_merge_progress,
            )
        except CodeScanPipelineMisconfiguredError as misconfig:
            logger.error("internal_ocr.misconfigured job_id=%s err=%s", job_id, misconfig)
            _publish_job_event(
                "job.failed",
                message=str(misconfig)[:500],
                error_code="INTERNAL_OCR_PIPELINE_MISCONFIGURED",
                severity="ERROR",
            )
            self._state.fail_job_and_aisle(
                job_id,
                aisle,
                str(misconfig),
                failure_code="INTERNAL_OCR_PIPELINE_MISCONFIGURED",
            )
            return True
        except Exception as unhandled:
            logger.exception("internal_ocr.unhandled_worker_error job_id=%s", job_id)
            _publish_job_event(
                "job.failed",
                message=type(unhandled).__name__,
                error_code="UNHANDLED_WORKER_ERROR",
                severity="ERROR",
                metadata={"error_type": type(unhandled).__name__},
            )
            self._state.fail_job_and_aisle(
                job_id,
                aisle,
                f"Unhandled INTERNAL_OCR worker error: {type(unhandled).__name__}",
                failure_code="UNHANDLED_WORKER_ERROR",
            )
            raise

        merge_payload: dict = {"asset_progress": progress_to_public_dict(outcome.progress)}
        if external_fallback is not None:
            from src.application.services.image_processing.external_provider_fallback_orchestrator import (
                resolve_fallback_progress_payload,
            )

            merge_payload.update(
                resolve_fallback_progress_payload(
                    job_id=job_id,
                    external_fallback=external_fallback,
                    external_request_repo=external_request_repo,
                    resolved_internal=int(getattr(outcome.progress, "resolved", 0) or 0),
                )
            )
        self._job_repo.merge_result_json(job_id, merge_payload)

        job_outcome = outcome.job_outcome

        if job_outcome is CodeScanJobOutcome.CANCELLED:
            current = self._job_repo.get_by_id(job_id)
            if current is not None and current.status == JobStatus.RUNNING:
                return self._cancellation_coordinator.handle_pipeline_cancellation(
                    job_id=job_id,
                    aisle=aisle,
                    error=PipelineCancellationRequestedError(outcome.error_message or "cancelled"),
                    exec_log=exec_log,
                    cancel_event_emitted=cancel_event_emitted,
                )
            return True

        if job_outcome is CodeScanJobOutcome.FAILED:
            current = self._job_repo.get_by_id(job_id)
            if current is not None and current.status == JobStatus.RUNNING:
                _publish_job_event(
                    "job.failed",
                    message=(outcome.error_message or "internal_ocr_failed")[:500],
                    error_code="INTERNAL_OCR_FAILED",
                    severity="ERROR",
                )
                self._state.fail_job_and_aisle(
                    job_id,
                    aisle,
                    outcome.error_message or "internal_ocr_failed",
                    failure_code="INTERNAL_OCR_FAILED",
                )
            return True

        progress = outcome.progress
        if global_fallback_ctx is not None:
            gf = self._run_global_external_fallback_after_internal(
                job=job,
                aisle=aisle,
                assets=assets,
                settings=settings,
                is_cancelled=_is_cancelled,
                event_publisher=event_publisher,
                state_repo=state_repo,
                lease_repo=lease_repo,
                ctx=global_fallback_ctx,
            )
            if gf is False:
                return True

        _publish_job_event(
            "job.finalization_started",
            message="INTERNAL_OCR finalization started",
            metadata={
                "resolved": int(getattr(progress, "resolved", 0) or 0),
                "manual_review": int(getattr(progress, "manual_review", 0) or 0),
                "unrecognized": int(getattr(progress, "unrecognized", 0) or 0),
                "failed_technical": int(getattr(progress, "failed", 0) or 0),
            },
        )

        self._job_repo.merge_result_json(job_id, {"internal_ocr_outcome": job_outcome.value})
        if job_outcome is CodeScanJobOutcome.PARTIALLY_COMPLETED:
            self._job_repo.merge_result_json(job_id, {"internal_ocr_partial": True})

        try:
            if _is_cancelled():
                logger.warning("internal_ocr.aborted_before_success_finalization job_id=%s", job_id)
                return True
            self._state.finalize_code_scan_success(job_id, aisle)
        except Exception as exc:
            logger.exception("internal_ocr.finalize_failed job_id=%s", job_id)
            _publish_job_event(
                "job.failed",
                message=f"internal_ocr finalization failed: {type(exc).__name__}",
                error_code="INTERNAL_OCR_FINALIZATION_FAILED",
                severity="ERROR",
            )
            self._state.fail_job_and_aisle(
                job_id,
                aisle,
                f"internal_ocr finalization failed: {exc}",
                failure_code="INTERNAL_OCR_FINALIZATION_FAILED",
            )
            return True

        completed_event = (
            "job.partially_completed"
            if job_outcome is CodeScanJobOutcome.PARTIALLY_COMPLETED
            else "job.completed"
        )
        _publish_job_event(
            completed_event,
            message=f"INTERNAL_OCR {job_outcome.value}",
            metadata={
                "resolved": int(getattr(progress, "resolved", 0) or 0),
                "manual_review": int(getattr(progress, "manual_review", 0) or 0),
                "unrecognized": int(getattr(progress, "unrecognized", 0) or 0),
                "failed_technical": int(getattr(progress, "failed", 0) or 0),
                "status": job_outcome.value,
            },
        )
        return True

    def _v3_run_job_body(self, base_path: Path, job_id: str, prep: V3PreparedJob) -> bool:
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

        snapshot_required = bool(settings.observability_input_snapshot_required)
        try:
            from src.application.errors import InputSnapshotPersistError
            from src.application.services.job_source_asset_snapshot import (
                persist_job_source_asset_snapshot_checked,
            )

            snapshot_result = persist_job_source_asset_snapshot_checked(
                self._job_source_asset_repo,
                job_id=job_id,
                assets=assets,
                stage="SOURCE_ASSETS_RESOLVED",
                required=snapshot_required,
            )
        except InputSnapshotPersistError as exc:
            logger.error(
                "job_source_asset_snapshot_failed_required job_id=%s code=%s err=%s",
                job_id,
                exc.code,
                exc,
            )
            self._state.fail_job_and_aisle(job_id, aisle, str(exc), failure_code=exc.code)
            return True
        except Exception as exc:
            if snapshot_required:
                logger.error(
                    "job_source_asset_snapshot_unexpected_error job_id=%s err=%s", job_id, exc
                )
                self._state.fail_job_and_aisle(
                    job_id,
                    aisle,
                    f"Input snapshot build failed: {exc}",
                    failure_code="INPUT_SNAPSHOT_PERSIST_FAILED",
                )
                return True
            logger.exception(
                "job_source_asset_snapshot_unexpected_error job_id=%s (continuing, not required)",
                job_id,
            )
        else:
            if not snapshot_result.ok:
                logger.warning(
                    "job_source_asset_snapshot_failed_not_required job_id=%s warning=%s",
                    job_id,
                    snapshot_result.warning,
                )
                current_job = self._job_repo.get_by_id(job_id)
                if current_job is not None:
                    result_json = dict(current_job.result_json or {})
                    result_json["input_snapshot_failed"] = True
                    result_json["input_snapshot_warning"] = snapshot_result.warning
                    current_job.result_json = result_json
                    self._job_repo.save(current_job)

        monitoring_req = V3JobMonitoringRequest(
            base_path=base_path,
            job_id=job_id,
            job_dir=job_dir,
            job=job,
            aisle=aisle,
            aisle_id=aisle_id,
        )
        with self._monitoring_service.session(monitoring_req) as rt:

            def execution_observer(
                stage: str, substep: str | None, event: str, details: dict[str, Any] | None
            ) -> None:
                self._state.update_runtime_status(
                    job_id,
                    stage=stage,
                    substep=substep,
                )

            cancellation_checkpoint = self._cancellation_coordinator.checkpoint(
                job_id=job_id,
                exec_log=rt.exec_log,
                inventory_id=aisle.inventory_id,
                aisle_id=aisle_id,
                cancel_event_emitted=rt.cancel_event_emitted,
            )

            try:

                def _run_legacy_pipeline_and_finalize() -> Any:
                    from src.application.services.image_processing.legacy_llm_processing_strategy import (
                        LegacyBatchOutcome,
                    )
                    from src.infrastructure.pipeline.v3_image_processing_bridge import (
                        assets_with_result_from_evidence,
                    )

                    pipeline_out = self._pipeline_execution_service.run(
                        V3PipelineExecutionRequest(
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
                    if pipeline_out is None:
                        return LegacyBatchOutcome(
                            ok=False, error_message="pipeline_execution_returned_none"
                        )
                    report = pipeline_out.report
                    result = pipeline_out.pipeline_result
                    report_path = pipeline_out.report_path
                    finalized = self._finalization_service.finalize_success(
                        V3JobFinalizationRequest(
                            job_id=job_id,
                            aisle=aisle,
                            aisle_id=aisle_id,
                            run_dir=rt.run_dir,
                            exec_log=rt.exec_log,
                            pipeline_result=result,
                            report_path=report_path,
                            report=report,
                            job=job,
                            cancellation_checkpoint=cancellation_checkpoint,
                            cancel_event_emitted=rt.cancel_event_emitted,
                            input_type=getattr(job_input, "input_type", None),
                            canonical_traceability_expected=(
                                getattr(job_input, "input_type", "") == "photos"
                                and job.job_type == "process_aisle"
                            ),
                        )
                    )
                    with_result = assets_with_result_from_evidence(
                        self._result_evidence_repo, job_id
                    )
                    return LegacyBatchOutcome(
                        ok=bool(finalized),
                        report=report if isinstance(report, dict) else None,
                        pipeline_result=result,
                        report_path=str(report_path) if report_path is not None else None,
                        assets_with_result=with_result,
                        error_message=None if finalized else "finalization_failed",
                    )

                from src.domain.aisle_identification.modes import (
                    AisleIdentificationExecutionStrategy,
                )

                # Trust immutable execution_strategy only (feature flags applied at job start).
                if job.execution_strategy == AisleIdentificationExecutionStrategy.CODE_SCAN:
                    return self._run_code_scan_path(
                        job=job,
                        aisle=aisle,
                        aisle_id=aisle_id,
                        assets=assets,
                        settings=settings,
                        exec_log=rt.exec_log,
                        cancel_event_emitted=rt.cancel_event_emitted,
                        runtime_abort_event=rt.runtime_abort_event,
                        global_fallback_ctx=_GlobalFallbackRuntimeCtx(
                            base_path=base_path,
                            v3_base=v3_base,
                            job_dir=job_dir,
                            run_dir=rt.run_dir,
                            log=rt.log,
                            execution_observer=execution_observer,
                            cancellation_checkpoint=cancellation_checkpoint,
                            legacy_local_read_enabled=bool(
                                getattr(
                                    settings,
                                    "artifact_storage_legacy_local_read_enabled",
                                    False,
                                )
                            ),
                        ),
                    )

                if job.execution_strategy == AisleIdentificationExecutionStrategy.INTERNAL_OCR:
                    return self._run_internal_ocr_path(
                        job=job,
                        aisle=aisle,
                        aisle_id=aisle_id,
                        assets=assets,
                        settings=settings,
                        exec_log=rt.exec_log,
                        cancel_event_emitted=rt.cancel_event_emitted,
                        runtime_abort_event=rt.runtime_abort_event,
                        global_fallback_ctx=_GlobalFallbackRuntimeCtx(
                            base_path=base_path,
                            v3_base=v3_base,
                            job_dir=job_dir,
                            run_dir=rt.run_dir,
                            log=rt.log,
                            execution_observer=execution_observer,
                            cancellation_checkpoint=cancellation_checkpoint,
                            legacy_local_read_enabled=bool(
                                getattr(
                                    settings,
                                    "artifact_storage_legacy_local_read_enabled",
                                    False,
                                )
                            ),
                        ),
                    )

                if bool(settings.image_processing_orchestrator_enabled):
                    import uuid as _uuid

                    from src.application.errors import ImageProcessingRepositoryUnavailableError
                    from src.domain.jobs.entities import JobStatus
                    from src.infrastructure.pipeline.v3_image_processing_bridge import (
                        build_default_aisle_processing_orchestrator,
                        progress_to_public_dict,
                        run_orchestrated_legacy_batch,
                    )
                    from src.runtime.app_container import get_app_container

                    container = get_app_container()
                    require_sql = container.is_sql_repository_backend()
                    try:
                        state_repo = container.get_job_asset_processing_state_repo()
                        attempt_repo = container.get_processing_attempt_repo()
                        lease_repo = container.get_job_processing_lease_repo()
                        batch_attempt_repo = container.get_batch_processing_attempt_repo()
                    except Exception as repo_exc:
                        logger.error(
                            "image_orchestrator.repo_resolve_failed job_id=%s require_sql=%s",
                            job_id,
                            require_sql,
                            exc_info=True,
                        )
                        if require_sql:
                            self._state.fail_job_and_aisle(
                                job_id,
                                aisle,
                                f"Phase 2 SQL image-processing repositories unavailable: {repo_exc}",
                                failure_code="IMAGE_PROCESSING_REPOSITORY_UNAVAILABLE",
                            )
                            return True
                        state_repo = None
                        attempt_repo = None
                        lease_repo = None
                        batch_attempt_repo = None

                    try:
                        orch = build_default_aisle_processing_orchestrator(
                            self._clock,
                            attempts_enabled=bool(settings.processing_attempts_enabled),
                            state_repo=state_repo,
                            attempt_repo=attempt_repo,
                            lease_repo=lease_repo,
                            batch_attempt_repo=batch_attempt_repo,
                            result_evidence_repo=self._result_evidence_repo,
                            evidence_repo=self._evidence_repo,
                            position_repo=self._position_repo,
                            require_sql=require_sql,
                            lease_duration_seconds=settings.image_processing_batch_lease_seconds,
                            abandoned_processing_ttl_seconds=(
                                settings.image_processing_abandoned_ttl_seconds
                            ),
                        )
                    except ImageProcessingRepositoryUnavailableError as unavailable:
                        logger.error(
                            "image_orchestrator.repos_unavailable job_id=%s err=%s",
                            job_id,
                            unavailable,
                        )
                        self._state.fail_job_and_aisle(
                            job_id,
                            aisle,
                            str(unavailable),
                            failure_code="IMAGE_PROCESSING_REPOSITORY_UNAVAILABLE",
                        )
                        return True

                    def _is_cancelled() -> bool:
                        current = self._job_repo.get_by_id(job_id)
                        return current is not None and current.status == JobStatus.CANCEL_REQUESTED

                    orch_out = run_orchestrated_legacy_batch(
                        orchestrator=orch,
                        job=job,
                        aisle=aisle,
                        assets=assets,
                        pipeline_enabled=bool(settings.aisle_identification_pipeline_enabled),
                        orchestrator_enabled=True,
                        is_cancelled=_is_cancelled,
                        worker_token=str(_uuid.uuid4()),
                        batch_runner=lambda: _run_legacy_pipeline_and_finalize(),
                    )
                    # Prefer repository-level merge so concurrent writers of other result_json
                    # keys (costs, durable artifacts, etc.) are not wiped by a full RMW.
                    self._job_repo.merge_result_json(
                        job_id,
                        {"asset_progress": progress_to_public_dict(orch_out.progress)},
                    )

                    # Preserve exact legacy semantics: orchestrator must not turn a failed or
                    # cancelled legacy batch into an implicit success just because bookkeeping ran.
                    if orch_out.legacy.cancelled:
                        current = self._job_repo.get_by_id(job_id)
                        if current is not None and current.status == JobStatus.RUNNING:
                            return self._cancellation_coordinator.handle_pipeline_cancellation(
                                job_id=job_id,
                                aisle=aisle,
                                error=PipelineCancellationRequestedError(
                                    orch_out.legacy.error_message or "cancelled"
                                ),
                                exec_log=rt.exec_log,
                                cancel_event_emitted=rt.cancel_event_emitted,
                            )
                        return True

                    if not orch_out.legacy.ok:
                        msg = orch_out.legacy.error_message or "legacy_batch_failed"
                        code = (
                            "BATCH_LEASE_NOT_ACQUIRED"
                            if orch_out.legacy.skipped_busy
                            else "LEGACY_BATCH_FAILED"
                        )
                        current = self._job_repo.get_by_id(job_id)
                        # finalize_success may already have marked FAILED; only fail if still RUNNING.
                        if current is not None and current.status == JobStatus.RUNNING:
                            self._state.fail_job_and_aisle(job_id, aisle, msg, failure_code=code)
                        return True

                    return True

                # Flag off: exact pre-Phase-2 legacy path (functional equivalence).
                pipeline_out = self._pipeline_execution_service.run(
                    V3PipelineExecutionRequest(
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
                if pipeline_out is None:
                    return True
                report = pipeline_out.report
                result = pipeline_out.pipeline_result
                report_path = pipeline_out.report_path

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
                if self._finalization_service.finalize_success(
                    V3JobFinalizationRequest(
                        job_id=job_id,
                        aisle=aisle,
                        aisle_id=aisle_id,
                        run_dir=rt.run_dir,
                        exec_log=rt.exec_log,
                        pipeline_result=result,
                        report_path=report_path,
                        report=report,
                        job=job,
                        cancellation_checkpoint=cancellation_checkpoint,
                        cancel_event_emitted=rt.cancel_event_emitted,
                        input_type=getattr(job_input, "input_type", None),
                        canonical_traceability_expected=(
                            getattr(job_input, "input_type", "") == "photos"
                            and job.job_type == "process_aisle"
                        ),
                    )
                ):
                    return True
            except PipelineCancellationRequestedError as e:
                return self._cancellation_coordinator.handle_pipeline_cancellation(
                    job_id=job_id,
                    aisle=aisle,
                    error=e,
                    exec_log=rt.exec_log,
                    cancel_event_emitted=rt.cancel_event_emitted,
                )
            except Exception as e:
                return self._failure_handler.handle_unexpected_failure(
                    V3WorkerFailureRequest(
                        job_id=job_id,
                        aisle=aisle,
                        aisle_id=aisle_id,
                        run_dir=rt.run_dir,
                        error=e,
                    )
                )

        return True
