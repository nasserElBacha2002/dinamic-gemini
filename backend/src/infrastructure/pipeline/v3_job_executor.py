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

from src.application.ports.clock import Clock
from src.application.ports.job_result_unit_of_work import JobResultUnitOfWorkFactory
from src.application.ports.repositories import (
    AisleRepository,
    ClientSupplierRepository,
    EvidenceRepository,
    InventoryRepository,
    JobRepository,
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
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.services.job_engine_params import coerce_prompt_parity_mode
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
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.pipeline.hybrid_report_to_domain_adapter import (
    default_map_hybrid_report_to_domain,
)
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
        recompute_consolidated_uc: RecomputeConsolidatedCountsUseCase | None = None,
        job_result_uow_factory: JobResultUnitOfWorkFactory | None = None,
        client_supplier_repo: ClientSupplierRepository | None = None,
        supplier_prompt_config_repo: SupplierPromptConfigRepository | None = None,
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
        self._persist_use_case = PersistAisleResultUseCase(
            position_repo=position_repo,
            product_record_repo=product_record_repo,
            evidence_repo=evidence_repo,
            clock=clock,
            hybrid_mapper=default_map_hybrid_report_to_domain,
            aisle_repo=aisle_repo,
            raw_label_repo=raw_label_repo,
            recompute_consolidated_uc=recompute_consolidated_uc,
            job_result_uow_factory=job_result_uow_factory,
        )
        self._heartbeat_interval_sec = 10

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
        """Persist domain, upload durables, mark_success. True => caller must return True (failure)."""
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
            p.exec_log.info("Persist", "Persist completed")
        except Exception as persist_e:
            p.exec_log.error(
                "Persist",
                f"Persist failed: {persist_e}",
                payload={"error": str(persist_e)[:500]},
            )
            self._state.fail_job_and_aisle(p.job_id, p.aisle, f"Persist: {persist_e}")
            return True

        logger.info(
            "v3_job_domain_persist_complete job_id=%s aisle_id=%s next_step=durable_artifact_upload",
            p.job_id,
            p.aisle_id,
        )

        try:
            self._artifacts.require_store()
        except RuntimeError as store_err:
            msg = str(store_err)
            logger.error("v3_job_id=%s %s", p.job_id, msg)
            p.exec_log.error("Artifacts", msg)
            self._state.fail_job_and_aisle(p.job_id, p.aisle, msg)
            return True
        try:
            p.cancellation_checkpoint(
                "Artifacts",
                "pre_upload",
                "Job canceled before artifact upload",
            )
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
        except Exception as artifact_exc:
            logger.exception(
                "worker_durable_artifact_publish_failed job_id=%s",
                p.job_id,
            )
            logger.error(
                "v3_job_finalization_partial_state job_id=%s aisle_id=%s "
                "domain_persist_completed=true durable_upload_succeeded=false "
                "operator_hint=%s",
                p.job_id,
                p.aisle_id,
                "PersistAisleResult may have committed domain data; job/aisle FAILED; "
                "no durable_artifacts in DB. Ops: inspect aisle/product state; use new job or "
                "reset workflow if reprocessing is required.",
            )
            p.exec_log.error(
                "Artifacts",
                f"Durable artifact upload failed: {artifact_exc}",
                payload={"error": str(artifact_exc)[:500]},
            )
            self._state.fail_job_and_aisle(
                p.job_id,
                p.aisle,
                f"Durable artifact upload failed: {artifact_exc}",
            )
            return True

        self._state.mark_success(
            p.job_id,
            p.aisle,
            p.report_path,
            run_metadata=p.result.run_metadata,
            durable_artifacts=durable_meta,
        )
        logger.info(
            "v3 mark success: job_id=%s inventory_id=%s aisle_id=%s report_path=%s",
            p.job_id,
            p.aisle.inventory_id,
            p.aisle_id,
            str(p.report_path),
        )
        return False

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
