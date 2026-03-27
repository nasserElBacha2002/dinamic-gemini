"""
V3 process_aisle job executor — Épica 6.

Resolves aisle assets, runs the hybrid pipeline, maps report to v3 domain,
persists positions/product_records/evidences, and updates job/aisle status.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Optional

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
from src.application.services.aisle_analysis_context_builder import (
    AisleAnalysisContextBuilder,
)
from src.application.use_cases.recompute_consolidated_counts import RecomputeConsolidatedCountsUseCase
from src.config import load_settings
from src.domain.aisle.entities import Aisle
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.jobs.entities import Job, JobStatus
from src.io.logging import setup_logger
from src.jobs.models import JobInput
from src.pipeline.contracts.analysis_context import (
    AnalysisContext,
    AnalysisImage,
    VisualReferenceContext,
    analysis_context_to_dict,
)
from src.pipeline.execution_log import ExecutionLogWriter, read_last_stage_error
from src.pipeline.hybrid_inventory_pipeline import HybridInventoryPipeline, PipelineRunResult
from src.pipeline.run_metadata import (
    RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT,
    default_empty_block,
)

logger = logging.getLogger(__name__)

RUN_ID = "run"


def _resolve_visual_reference_paths(ctx: AnalysisContext, v3_base: Path) -> AnalysisContext:
    """Return a new AnalysisContext with resolved_path set on each visual reference. Provider consumes these paths."""
    if not ctx.visual_references:
        return ctx
    resolved_refs = [
        VisualReferenceContext(
            reference_id=ref.reference_id,
            source_path=ref.source_path,
            mime_type=ref.mime_type,
            role=ref.role,
            created_at=ref.created_at,
            resolved_path=str(v3_base / ref.source_path),
        )
        for ref in ctx.visual_references
    ]
    return AnalysisContext(
        primary_evidence=ctx.primary_evidence,
        visual_references=resolved_refs,
        instructions=ctx.instructions,
        metadata=ctx.metadata,
    )


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
        raw_label_repo: RawLabelRepository | None = None,
        recompute_consolidated_uc: RecomputeConsolidatedCountsUseCase | None = None,
    ) -> None:
        self._job_repo = job_repo
        self._aisle_repo = aisle_repo
        self._inventory_repo = inventory_repo
        self._source_asset_repo = source_asset_repo
        self._position_repo = position_repo
        self._product_record_repo = product_record_repo
        self._evidence_repo = evidence_repo
        self._clock = clock
        self._inventory_status_reconciler = InventoryStatusReconciler(
            inventory_repo=inventory_repo,
            aisle_repo=aisle_repo,
            clock=clock,
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
        resolver = InventoryVisualReferenceResolver(
            inventory_repo=inventory_repo,
            reference_repo=inventory_visual_reference_repo,
        )
        self._context_builder = AisleAnalysisContextBuilder(resolver)

    def _reconcile_inventory_for_aisle(self, aisle: Aisle) -> None:
        self._inventory_status_reconciler.reconcile(aisle.inventory_id)

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
            self._cancel_job(job_id, "Job canceled before execution")
            return True
        if job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
            logger.warning("v3 job %s invalid status for execution (status=%s), skip", job_id, job.status.value)
            return True

        payload = job.payload_json or {}
        aisle_id = payload.get("aisle_id")
        if not aisle_id:
            self._fail_job(job_id, "Missing aisle_id in payload")
            return True

        aisle = self._aisle_repo.get_by_id(aisle_id)
        if aisle is None:
            self._fail_job(job_id, f"Aisle not found: {aisle_id}")
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
        if not assets:
            self._fail_job_and_aisle(job_id, aisle, "No source assets for aisle")
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
        self._mark_running(job_id, aisle, now)

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

        try:
            analysis_context = self._build_analysis_context(aisle)
            job_input, video_path = self._build_pipeline_input(
                assets, v3_base, job_dir, job_id, analysis_context=analysis_context
            )
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
            self._fail_job_and_aisle(job_id, aisle, str(e))
            return True

        run_dir = base_path / job_id / RUN_ID
        log = setup_logger(str(job_dir), job_id, RUN_ID, console=False)
        logger.info(
            "v3 execution log initialized: job_id=%s run_dir=%s",
            job_id,
            str(run_dir),
        )

        try:
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
            result = pipeline.process_video(
                video_path,
                mode="hybrid",
                settings=settings,
                video_id=job_id,
                output_path=base_path,
                run_id=RUN_ID,
                logger=log,
                progress_callback=None,
                job_input=job_input,
                analysis_context=analysis_context,
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
                self._fail_job_and_aisle(job_id, aisle, error_message)
                return True

            # Cooperative cancellation checkpoint after pipeline execution and before persist.
            current_job = self._job_repo.get_by_id(job_id)
            if current_job is not None and current_job.status == JobStatus.CANCEL_REQUESTED:
                logger.info("v3 job %s cancellation observed after pipeline; marking canceled", job_id)
                self._cancel_job_and_aisle(job_id, aisle, "Job canceled after pipeline execution")
                return True

            report_path = run_dir / "hybrid_report.json"
            if not report_path.exists():
                self._fail_job_and_aisle(
                    job_id, aisle, "Reporting error: Pipeline did not produce hybrid_report.json"
                )
                return True

            with open(report_path, encoding="utf-8") as f:
                report = json.load(f)

            exec_log = ExecutionLogWriter(run_dir)
            exec_log.info("Persist", "Persist started", payload={"aisle_id": aisle_id})
            try:
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
                self._fail_job_and_aisle(job_id, aisle, f"Persist: {persist_e}")
                return True

            # Phase 5: persist visual_reference_context from in-memory run_metadata (no file read)
            self._mark_success(
                job_id, aisle, report_path, now, run_metadata=result.run_metadata
            )
            logger.info(
                "v3 mark success: job_id=%s inventory_id=%s aisle_id=%s report_path=%s",
                job_id,
                aisle.inventory_id,
                aisle_id,
                str(report_path),
            )
        except Exception as e:
            logger.exception("v3 job %s failed: %s", job_id, e)
            run_dir = base_path / job_id / RUN_ID
            if run_dir.is_dir():
                try:
                    exec_log = ExecutionLogWriter(run_dir)
                    exec_log.error("Pipeline", f"Job failed: {e}", payload={"error": str(e)[:500]})
                except Exception:
                    pass
            self._fail_job_and_aisle(job_id, aisle, str(e))
            logger.info(
                "v3 mark failed: job_id=%s inventory_id=%s aisle_id=%s error=%s",
                job_id,
                aisle.inventory_id,
                aisle_id,
                str(e),
            )

        return True

    def _build_analysis_context(self, aisle: Aisle) -> AnalysisContext:
        """Construct AnalysisContext for this aisle's inventory. Primary evidence left empty in v3.2.4."""
        inventory_id = aisle.inventory_id
        primary: list[AnalysisImage] = []
        return self._context_builder.build(
            inventory_id=inventory_id,
            primary_evidence=primary,
            metadata=None,
        )

    def _build_pipeline_input(
        self,
        assets: list,
        v3_base: Path,
        job_dir: Path,
        job_id: str,
        *,
        analysis_context: AnalysisContext,
    ) -> tuple:
        """Return (JobInput, video_path). video_path used as first arg to process_video."""
        single_video = (
            len(assets) == 1
            and getattr(assets[0], "type", None) == SourceAssetType.VIDEO
        )
        if single_video:
            asset = assets[0]
            full = v3_base / asset.storage_path
            if not full.exists():
                raise FileNotFoundError(f"Asset file not found: {full}")
            video_path = str(full)
            resolved_ctx = _resolve_visual_reference_paths(analysis_context, v3_base)
            return (
                JobInput(
                    video_path=video_path,
                    mode="hybrid",
                    input_type="video",
                    metadata={"analysis_context": analysis_context_to_dict(resolved_ctx)},
                ),
                video_path,
            )

        # Photos execution supports only photo assets. Any video in a multi-asset
        # set would be routed into image normalization and fail opaquely later.
        has_video_asset = any(getattr(a, "type", None) == SourceAssetType.VIDEO for a in assets)
        if has_video_asset:
            raise ValueError(
                "Invalid aisle assets: videos must be uploaded/processed as a single video asset; "
                "mixed or multi-video sets are not supported in photos normalization flow."
            )

        # Photos (or multiple assets): copy into job_dir/input_photos, write manifest
        photos_dir = job_dir / "input_photos"
        photos_dir.mkdir(parents=True, exist_ok=True)
        photos_list = []
        for i, asset in enumerate(assets):
            src = v3_base / asset.storage_path
            if not src.exists():
                raise FileNotFoundError(f"Asset file not found: {src}")
            ext = Path(asset.storage_path).suffix or ".jpg"
            stored = f"{i:04d}_{asset.id}{ext}"
            dst = photos_dir / stored
            if dst != src:
                shutil.copy2(src, dst)
            # Expose image_id (asset.id) so pipeline/LLM use it as source_image_id; enables reference-image view.
            photos_list.append({
                "index": i + 1,  # 1-based for load_job_images_from_manifest
                "image_id": asset.id,
                "original_filename": asset.original_filename,
                "stored_filename": stored,
            })

        manifest_path = job_dir / "input_manifest.json"
        manifest = {
            "input_type": "photos",
            "photos": photos_list,
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        # Paths relative to job dir for pipeline
        resolved_ctx = _resolve_visual_reference_paths(analysis_context, v3_base)
        return (
            JobInput(
                video_path="",
                mode="hybrid",
                input_type="photos",
                input_manifest_path="input_manifest.json",
                photos_dir="input_photos",
                metadata={"analysis_context": analysis_context_to_dict(resolved_ctx)},
            ),
            "",  # video_path empty for photos
        )

    def _mark_running(self, job_id: str, aisle: Aisle, now) -> None:
        job = self._job_repo.get_by_id(job_id)
        if job:
            job.status = JobStatus.RUNNING
            job.updated_at = now
            self._job_repo.save(job)
        aisle.mark_processing(now)
        self._aisle_repo.save(aisle)
        self._reconcile_inventory_for_aisle(aisle)

    def _mark_success(
        self,
        job_id: str,
        aisle: Aisle,
        report_path: Path,
        now,
        *,
        run_metadata: Optional[dict] = None,
    ) -> None:
        job = self._job_repo.get_by_id(job_id)
        if job:
            job.status = JobStatus.SUCCEEDED
            job.updated_at = now
            meta = run_metadata or {}
            vrc = meta.get(RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT)
            job.result_json = {
                "report_path": str(report_path),
                RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT: vrc
                if vrc is not None
                else default_empty_block(),
                "provider": meta.get("provider"),
            }
            if meta.get("prompt_key"):
                job.result_json["prompt_key"] = meta["prompt_key"]
            job.error_message = None
            self._job_repo.save(job)
        aisle.mark_processed(now)
        self._aisle_repo.save(aisle)
        self._reconcile_inventory_for_aisle(aisle)

    def _fail_job(self, job_id: str, error_message: str) -> None:
        job = self._job_repo.get_by_id(job_id)
        if job:
            now = self._clock.now()
            job.status = JobStatus.FAILED
            job.updated_at = now
            job.error_message = error_message[:2048] if len(error_message) > 2048 else error_message
            self._job_repo.save(job)

    def _cancel_job(self, job_id: str, reason: str) -> None:
        job = self._job_repo.get_by_id(job_id)
        if job:
            now = self._clock.now()
            job.status = JobStatus.CANCELED
            job.updated_at = now
            job.error_message = reason[:2048] if len(reason) > 2048 else reason
            self._job_repo.save(job)

    def _fail_job_and_aisle(
        self, job_id: str, aisle: Aisle, error_message: str
    ) -> None:
        now = self._clock.now()
        self._fail_job(job_id, error_message)
        aisle.mark_failed(
            now,
            error_code="PROCESSING_FAILED",
            error_message=error_message[:2048] if len(error_message) > 2048 else error_message,
            retryable=True,
        )
        self._aisle_repo.save(aisle)
        self._reconcile_inventory_for_aisle(aisle)

    def _cancel_job_and_aisle(
        self, job_id: str, aisle: Aisle, reason: str
    ) -> None:
        now = self._clock.now()
        self._cancel_job(job_id, reason)
        aisle.mark_failed(
            now,
            error_code="CANCELED",
            error_message=reason[:2048] if len(reason) > 2048 else reason,
            retryable=True,
        )
        self._aisle_repo.save(aisle)
        self._reconcile_inventory_for_aisle(aisle)
