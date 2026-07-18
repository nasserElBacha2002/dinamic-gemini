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
        self._monitoring_service = V3JobMonitoringService(state_service=self._state)
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

        try:
            strategy = build_default_code_scan_strategy(settings, self._artifact_store)
            persister = build_default_code_scan_persister(
                job_source_asset_repo=container.get_job_source_asset_repo(),
                source_asset_repo=self._source_asset_repo,
                clock=self._clock,
                unit_of_work_factory=container.get_manual_image_result_uow_factory(),
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
                abandoned_processing_ttl_seconds=(
                    settings.image_processing_abandoned_ttl_seconds
                ),
                manual_coverage_repo=container.get_manual_image_coverage_repo(),
            )
        except ImageProcessingRepositoryUnavailableError as unavailable:
            logger.error(
                "code_scan.repos_unavailable job_id=%s err=%s", job_id, unavailable
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

        def _merge_progress(progress) -> None:
            self._job_repo.merge_result_json(
                job_id, {"asset_progress": progress_to_public_dict(progress)}
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
            self._state.fail_job_and_aisle(
                job_id,
                aisle,
                str(misconfig),
                failure_code="CODE_SCAN_PIPELINE_MISCONFIGURED",
            )
            return True

        self._job_repo.merge_result_json(
            job_id, {"asset_progress": progress_to_public_dict(outcome.progress)}
        )

        job_outcome = outcome.job_outcome

        if job_outcome is CodeScanJobOutcome.CANCELLED:
            current = self._job_repo.get_by_id(job_id)
            if current is not None and current.status == JobStatus.RUNNING:
                return self._cancellation_coordinator.handle_pipeline_cancellation(
                    job_id=job_id,
                    aisle=aisle,
                    error=PipelineCancellationRequestedError(
                        outcome.error_message or "cancelled"
                    ),
                    exec_log=exec_log,
                    cancel_event_emitted=cancel_event_emitted,
                )
            return True

        if job_outcome is CodeScanJobOutcome.FAILED:
            current = self._job_repo.get_by_id(job_id)
            if current is not None and current.status == JobStatus.RUNNING:
                self._state.fail_job_and_aisle(
                    job_id,
                    aisle,
                    outcome.error_message or "code_scan_failed",
                    failure_code="CODE_SCAN_FAILED",
                )
            return True

        # SUCCEEDED or PARTIALLY_COMPLETED — both are completed jobs. A partial run recorded
        # a mix of asset outcomes (some FAILED_TECHNICAL, some resolved/unrecognized/manual);
        # it is still a completed job, annotated in result_json for auditability.
        self._job_repo.merge_result_json(
            job_id, {"code_scan_outcome": job_outcome.value}
        )
        if job_outcome is CodeScanJobOutcome.PARTIALLY_COMPLETED:
            self._job_repo.merge_result_json(job_id, {"code_scan_partial": True})

        try:
            self._state.finalize_code_scan_success(job_id, aisle)
        except Exception as exc:
            logger.exception("code_scan.finalize_failed job_id=%s", job_id)
            self._state.fail_job_and_aisle(
                job_id,
                aisle,
                f"code_scan finalization failed: {exc}",
                failure_code="CODE_SCAN_FINALIZATION_FAILED",
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

                if (
                    job.execution_strategy
                    == AisleIdentificationExecutionStrategy.CODE_SCAN
                    and bool(settings.code_scan_processing_enabled)
                ):
                    return self._run_code_scan_path(
                        job=job,
                        aisle=aisle,
                        aisle_id=aisle_id,
                        assets=assets,
                        settings=settings,
                        exec_log=rt.exec_log,
                        cancel_event_emitted=rt.cancel_event_emitted,
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
                        pipeline_enabled=bool(
                            settings.aisle_identification_pipeline_enabled
                        ),
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
                            self._state.fail_job_and_aisle(
                                job_id, aisle, msg, failure_code=code
                            )
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
