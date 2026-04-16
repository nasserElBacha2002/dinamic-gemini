"""
V3 process_aisle job executor — Épica 6.

Thin coordinator: resolves aisle assets, delegates pipeline input + hybrid run, persists domain
results, durable artifacts, and job/aisle status via collaborators (Phase 2 split).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import threading
from typing import Any, Dict, Optional

from src.application.ports.clock import Clock
from src.application.ports.repositories import (
    AisleRepository,
    EvidenceRepository,
    InventoryRepository,
    InventoryVisualReferenceRepository,
    JobRepository,
    PositionRepository,
    ProductRecordRepository,
    RawLabelRepository,
    SourceAssetRepository,
)
from src.application.use_cases.persist_aisle_result import (
    PersistAisleResultCommand,
    PersistAisleResultUseCase,
)
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.services.inventory_visual_reference_resolver import (
    InventoryVisualReferenceResolver,
)
from src.application.services.job_engine_params import coerce_prompt_parity_mode
from src.application.services.aisle_analysis_context_builder import (
    AisleAnalysisContextBuilder,
)
from src.application.use_cases.recompute_consolidated_counts import RecomputeConsolidatedCountsUseCase
from src.config import load_settings
from src.domain.aisle.entities import Aisle
from src.domain.jobs.entities import Job, JobStatus
from src.io.logging import setup_logger
from src.pipeline.contracts.analysis_context import AnalysisContext, analysis_context_from_dict
from src.pipeline.errors import PipelineCancellationRequestedError
from src.pipeline.execution_log import ExecutionLogWriter, read_last_stage_error
from src.pipeline.hybrid_inventory_pipeline import HybridInventoryPipeline
from src.infrastructure.pipeline.worker_durable_artifact_publisher import (
    DEFAULT_V3_WORKER_RUN_SEGMENT,
)
from src.infrastructure.pipeline.v3_execution_artifacts_service import V3ExecutionArtifactsService
from src.infrastructure.pipeline.v3_job_execution_state import V3JobExecutionStateService
from src.infrastructure.pipeline.v3_process_aisle_pipeline_runner import (
    visual_reference_failure_metadata,
    V3ProcessAislePipelineRunner,
)
from src.jobs.worker_bootstrap import append_worker_bootstrap_event, checkpoint_v3_job_bootstrap
from src.pipeline.run_metadata import RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT

logger = logging.getLogger(__name__)

# Pipeline/output directory segment under {base}/{job_id}/; must match DEFAULT_V3_WORKER_RUN_SEGMENT.
RUN_ID = DEFAULT_V3_WORKER_RUN_SEGMENT


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
        inventory_visual_reference_repo: InventoryVisualReferenceRepository,
        artifact_store=None,
        raw_label_repo: RawLabelRepository | None = None,
        recompute_consolidated_uc: RecomputeConsolidatedCountsUseCase | None = None,
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
        resolver = InventoryVisualReferenceResolver(
            inventory_repo=inventory_repo,
            reference_repo=inventory_visual_reference_repo,
        )
        context_builder = AisleAnalysisContextBuilder(resolver)
        self._pipeline_runner = V3ProcessAislePipelineRunner(
            inventory_visual_reference_repo=inventory_visual_reference_repo,
            artifact_store=artifact_store,
            context_builder=context_builder,
        )
        self._persist_use_case = PersistAisleResultUseCase(
            position_repo=position_repo,
            product_record_repo=product_record_repo,
            evidence_repo=evidence_repo,
            clock=clock,
            aisle_repo=aisle_repo,
            raw_label_repo=raw_label_repo,
            recompute_consolidated_uc=recompute_consolidated_uc,
        )
        self._heartbeat_interval_sec = 10

    def execute(self, base_path: Path, job_id: str) -> bool:
        """
        If job_id is a v3 process_aisle job: load aisle/assets, run pipeline, persist, update status; return True.
        Otherwise return False (caller may run legacy flow).
        """
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
        if job.status == JobStatus.CANCELED:
            logger.info("v3 job %s already canceled, skip", job_id)
            return True
        if job.status == JobStatus.CANCEL_REQUESTED:
            logger.info("v3 job %s cancel requested before start; marking canceled", job_id)
            self._state.cancel_job(job, "Job canceled before execution", now=self._clock.now())
            return True
        if job.status != JobStatus.STARTING:
            logger.warning("v3 job %s invalid status for execution (status=%s), skip", job_id, job.status.value)
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

        analysis_context: Optional[AnalysisContext] = None
        try:
            analysis_context = self._pipeline_runner.build_analysis_context(aisle)
            job_input, video_path = self._pipeline_runner.build_pipeline_input(
                assets,
                v3_base,
                job_dir,
                job_id,
                analysis_context=analysis_context,
                inventory_id=aisle.inventory_id,
                run_id=RUN_ID,
                legacy_local_read_enabled=settings.artifact_storage_legacy_local_read_enabled,
            )
            resolved_analysis_context = analysis_context_from_dict(
                (job_input.metadata or {}).get("analysis_context")
            )
            if resolved_analysis_context is not None:
                analysis_context = resolved_analysis_context
            logger.info(
                "v3 pipeline input ready: job_id=%s inventory_id=%s aisle_id=%s input_type=%s video_path=%s",
                job_id,
                aisle.inventory_id,
                aisle_id,
                job_input.input_type,
                video_path or "",
            )
        except Exception as e:
            logger.exception("v3 job %s: build pipeline input failed: %s", job_id, e)
            if analysis_context is not None and analysis_context.visual_references:
                job = self._job_repo.get_by_id(job_id)
                if job is not None:
                    result_json = dict(job.result_json or {})
                    result_json[RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT] = visual_reference_failure_metadata(
                        analysis_context,
                        str(e),
                    )
                    job.result_json = result_json
                    self._job_repo.save(job)
            self._state.fail_job_and_aisle(job_id, aisle, str(e))
            return True

        assert analysis_context is not None

        run_dir = base_path / job_id / RUN_ID
        log = setup_logger(str(job_dir), job_id, RUN_ID, console=False)
        exec_log = ExecutionLogWriter(run_dir)
        exec_log.structured_event(
            job_id=job_id,
            inventory_id=aisle.inventory_id,
            aisle_id=aisle_id,
            attempt=job.attempt_count,
            stage="WorkerLaunch",
            substep="startup_confirmation",
            event="job.spawn_succeeded",
            details={"execution_id": job.execution_id},
        )
        logger.info(
            "v3 execution log initialized: job_id=%s run_dir=%s",
            job_id,
            str(run_dir),
        )

        stop_heartbeat = threading.Event()
        cancel_event_emitted: Dict[str, bool] = {"requested": False, "detected": False, "cancelled": False}

        def heartbeat_loop() -> None:
            while not stop_heartbeat.wait(self._heartbeat_interval_sec):
                current_job = self._state.heartbeat(job_id)
                if current_job is None:
                    continue
                exec_log.structured_event(
                    job_id=job_id,
                    inventory_id=aisle.inventory_id,
                    aisle_id=aisle_id,
                    attempt=current_job.attempt_count,
                    stage=current_job.current_stage or "Pipeline",
                    substep=current_job.current_substep,
                    event="job.heartbeat",
                )

        heartbeat_thread = threading.Thread(target=heartbeat_loop, name=f"job-heartbeat-{job_id}", daemon=True)
        heartbeat_thread.start()

        def execution_observer(stage: str, substep: Optional[str], event: str, details: Optional[Dict[str, Any]]) -> None:
            self._state.update_runtime_status(
                job_id,
                stage=stage,
                substep=substep,
            )

        def cancellation_checkpoint(stage: str, substep: Optional[str], reason: str) -> None:
            self._state.raise_if_cancellation_requested(
                job_id,
                exec_log=exec_log,
                inventory_id=aisle.inventory_id,
                aisle_id=aisle_id,
                stage=stage,
                substep=substep,
                reason=reason,
                cancel_event_emitted=cancel_event_emitted,
            )

        try:
            cancellation_checkpoint(
                "Pipeline",
                "pre_pipeline",
                "Job canceled before pipeline execution",
            )
            logger.info(
                "v3 executor start: job_id=%s job_type=%s target_type=%s target_id=%s inventory_id=%s aisle_id=%s",
                job_id,
                job.job_type,
                job.target_type,
                job.target_id,
                aisle.inventory_id,
                aisle_id,
            )
            pipeline = HybridInventoryPipeline()
            pipeline_provider_name = (job.provider_name or "").strip() or None
            job_model = (job.model_name or "").strip() or None
            job_prompt = (job.prompt_key or "").strip() or None
            job_prompt_version = (job.prompt_version or "").strip() or None
            job_prompt_parity_mode = coerce_prompt_parity_mode(job.engine_params_json)
            result = self._pipeline_runner.run_hybrid_pipeline(
                pipeline=pipeline,
                video_path=video_path,
                job_id=job_id,
                base_path=base_path,
                run_id=RUN_ID,
                settings=settings,
                job_input=job_input,
                analysis_context=analysis_context,
                log=log,
                execution_observer=execution_observer,
                cancellation_checkpoint=cancellation_checkpoint,
                pipeline_provider_name=pipeline_provider_name,
                job_model_name=job_model,
                job_prompt_key=job_prompt,
                job_prompt_version=job_prompt_version,
                job_prompt_parity_mode=job_prompt_parity_mode,
            )
            logger.info(
                "v3 executor finished: job_id=%s exit_code=%s inventory_id=%s aisle_id=%s",
                job_id,
                result.exit_code,
                aisle.inventory_id,
                aisle_id,
            )
            if result.exit_code != 0:
                last_error = read_last_stage_error(run_dir)
                if last_error:
                    error_message = f"{last_error} (exit code {result.exit_code})"
                else:
                    error_message = f"Pipeline exited with code {result.exit_code}"
                self._state.fail_job_and_aisle(job_id, aisle, error_message)
                return True

            # Cooperative cancellation checkpoint after pipeline execution and before persist.
            cancellation_checkpoint(
                "Pipeline",
                "post_pipeline",
                "Job canceled after pipeline execution",
            )

            report_path = run_dir / "hybrid_report.json"
            if not report_path.exists():
                self._state.fail_job_and_aisle(
                    job_id, aisle, "Reporting error: Pipeline did not produce hybrid_report.json"
                )
                return True

            with open(report_path, encoding="utf-8") as f:
                report = json.load(f)

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
            exec_log.info("Persist", "Persist started", payload={"aisle_id": aisle_id})
            try:
                cancellation_checkpoint(
                    "Persist",
                    "pre_persist",
                    "Job canceled before persistence",
                )
                self._persist_use_case.execute(
                    PersistAisleResultCommand(
                        aisle_id=aisle_id,
                        job_id=job_id,
                        report=report,
                        run_dir=run_dir,
                        run_id=RUN_ID,
                    )
                )
                exec_log.info("Persist", "Persist completed")
            except Exception as persist_e:
                exec_log.error("Persist", f"Persist failed: {persist_e}", payload={"error": str(persist_e)[:500]})
                # Record stage-prefixed failure in job/aisle state so diagnosability is explicit (Phase 4).
                # Do not re-raise: we have recorded the failure and return normally.
                self._state.fail_job_and_aisle(job_id, aisle, f"Persist: {persist_e}")
                return True

            logger.info(
                "v3_job_domain_persist_complete job_id=%s aisle_id=%s next_step=durable_artifact_upload",
                job_id,
                aisle_id,
            )

            # Phase 3B: durable execution outputs via ArtifactStore (S3 or local adapter).
            try:
                self._artifacts.require_store()
            except RuntimeError as store_err:
                msg = str(store_err)
                logger.error("v3_job_id=%s %s", job_id, msg)
                exec_log.error("Artifacts", msg)
                self._state.fail_job_and_aisle(job_id, aisle, msg)
                return True
            try:
                cancellation_checkpoint(
                    "Artifacts",
                    "pre_upload",
                    "Job canceled before artifact upload",
                )
                durable_meta = self._artifacts.publish_worker_durables(
                    job_id=job_id,
                    run_segment=RUN_ID,
                    run_dir=run_dir,
                )
                logger.info(
                    "worker_durable_artifacts_ready_for_job_metadata job_id=%s kinds=%s",
                    job_id,
                    sorted(durable_meta.keys()),
                )
            except Exception as artifact_exc:
                logger.exception(
                    "worker_durable_artifact_publish_failed job_id=%s",
                    job_id,
                )
                logger.error(
                    "v3_job_finalization_partial_state job_id=%s aisle_id=%s "
                    "domain_persist_completed=true durable_upload_succeeded=false "
                    "operator_hint=%s",
                    job_id,
                    aisle_id,
                    "PersistAisleResult may have committed domain data; job/aisle FAILED; "
                    "no durable_artifacts in DB. Ops: inspect aisle/product state; use new job or "
                    "reset workflow if reprocessing is required.",
                )
                exec_log.error(
                    "Artifacts",
                    f"Durable artifact upload failed: {artifact_exc}",
                    payload={"error": str(artifact_exc)[:500]},
                )
                self._state.fail_job_and_aisle(
                    job_id,
                    aisle,
                    f"Durable artifact upload failed: {artifact_exc}",
                )
                return True

            # Phase 5: persist visual_reference_context from in-memory run_metadata (no file read)
            self._state.mark_success(
                job_id,
                aisle,
                report_path,
                run_metadata=result.run_metadata,
                durable_artifacts=durable_meta,
            )
            logger.info(
                "v3 mark success: job_id=%s inventory_id=%s aisle_id=%s report_path=%s",
                job_id,
                aisle.inventory_id,
                aisle_id,
                str(report_path),
            )
        except PipelineCancellationRequestedError as e:
            logger.info("v3 job %s cancellation detected cooperatively: %s", job_id, e)
            self._state.cancel_job_and_aisle(
                job_id,
                aisle,
                str(e),
                exec_log=exec_log,
                cancel_event_emitted=cancel_event_emitted,
            )
            return True
        except Exception as e:
            logger.exception("v3 job %s failed: %s", job_id, e)
            run_dir = base_path / job_id / RUN_ID
            if run_dir.is_dir():
                try:
                    exec_log = ExecutionLogWriter(run_dir)
                    exec_log.error("Pipeline", f"Job failed: {e}", payload={"error": str(e)[:500]})
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
            stop_heartbeat.set()
            heartbeat_thread.join(timeout=1.0)

        return True
