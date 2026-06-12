"""Stage 7 — Background worker: pull jobs from queue and run inventory engine.
Stage 8 — When SQL Server enabled, push status/progress/outputs/pallet_results/events to DB.
Épica 6 — Try v3 process_aisle job first; fall back to legacy job record.
"""

import json
import logging
import time
from pathlib import Path
from typing import Callable, Optional

from src.config import load_settings
from src.io.logging import setup_logger
from src.jobs.job_store import _db_repos, claim_next_job, get_job, update_job
from src.jobs.models import JobStatus
from src.jobs.worker_bootstrap import (
    append_worker_bootstrap_event,
    checkpoint_v3_job_bootstrap,
    fail_v3_job_bootstrap,
)
from src.pipeline.hybrid_inventory_pipeline import HybridInventoryPipeline

logger = logging.getLogger(__name__)


def _mark_v3_job_failed(
    job_id: str,
    error_message: str,
    *,
    execution_id: str | None = None,
    substep: str = "bootstrap_failed",
) -> None:
    """Persist FAILED on the v3 job row when setup/executor fails (legacy store will not have this id)."""
    try:
        fail_v3_job_bootstrap(
            job_id=job_id,
            execution_id=execution_id,
            error_message=error_message,
            substep=substep,
        )
        logger.warning("v3 job_id=%s marked FAILED (worker setup/executor error)", job_id)
    except Exception:
        logger.warning("could not mark v3 job_id=%s as FAILED", job_id, exc_info=True)


def _try_v3_process_aisle(base_path: Path, job_id: str, *, execution_id: str | None = None) -> bool:
    """If job_id is a v3 process_aisle job, run it and return True. Otherwise return False."""
    try:
        logger.info("worker dispatch attempt: job_id=%s dispatch=v3_process_aisle", job_id)
        append_worker_bootstrap_event(
            job_id=job_id,
            execution_id=execution_id,
            event="worker.job_load_started",
            details={"dispatch": "v3_process_aisle"},
        )
        checkpoint_v3_job_bootstrap(
            job_id=job_id,
            execution_id=execution_id,
            substep="job_load_started",
        )
        from src.domain.jobs.entities import JobStatus as V3JobStatus
        from src.infrastructure.pipeline.v3_job_executor import V3JobExecutor
        from src.runtime.v3_deps import (
            get_aisle_repo,
            get_artifact_manifest_store,
            get_artifact_publication_outbox_store,
            get_artifact_staging_store,
            get_artifact_store,
            get_client_supplier_repo,
            get_clock,
            get_evidence_repo,
            get_final_count_repo,
            get_finalization_stage_store,
            get_inventory_repo,
            get_job_repo,
            get_job_result_uow_factory,
            get_job_scoped_recompute_factory,
            get_normalized_label_repo,
            get_operational_result_promotion_service,
            get_position_repo,
            get_product_record_repo,
            get_raw_label_repo,
            get_recompute_consolidated_counts_use_case,
            get_source_asset_repo,
            get_supplier_prompt_config_repo,
            get_supplier_reference_image_repo,
        )

        job_repo = get_job_repo()
        job = job_repo.get_by_id(job_id)
        append_worker_bootstrap_event(
            job_id=job_id,
            execution_id=execution_id or (job.execution_id if job is not None else None),
            event="worker.job_load_completed",
            details={
                "job_found": job is not None,
                "job_type": getattr(job, "job_type", None),
                "target_type": getattr(job, "target_type", None),
                "target_id": getattr(job, "target_id", None),
                "status": getattr(getattr(job, "status", None), "value", None),
            },
        )
        if job is not None and job.status in (
            V3JobStatus.STARTING,
            V3JobStatus.RUNNING,
            V3JobStatus.CANCEL_REQUESTED,
        ):
            checkpoint_v3_job_bootstrap(
                job_id=job_id,
                execution_id=execution_id or job.execution_id,
                substep="job_load_completed",
            )

        append_worker_bootstrap_event(
            job_id=job_id,
            execution_id=execution_id or (job.execution_id if job is not None else None),
            event="worker.executor_bootstrap_started",
            details={"base_path": str(base_path)},
        )
        executor = V3JobExecutor(
            job_repo=job_repo,
            aisle_repo=get_aisle_repo(),
            source_asset_repo=get_source_asset_repo(),
            position_repo=get_position_repo(),
            product_record_repo=get_product_record_repo(),
            evidence_repo=get_evidence_repo(),
            clock=get_clock(),
            inventory_repo=get_inventory_repo(),
            supplier_reference_image_repo=get_supplier_reference_image_repo(),
            artifact_store=get_artifact_store(),
            raw_label_repo=get_raw_label_repo(),
            normalized_label_repo=get_normalized_label_repo(),
            final_count_repo=get_final_count_repo(),
            job_scoped_recompute_factory=get_job_scoped_recompute_factory(),
            job_result_uow_factory=get_job_result_uow_factory(),
            recompute_consolidated_uc=get_recompute_consolidated_counts_use_case(),
            operational_promotion_service=get_operational_result_promotion_service(),
            client_supplier_repo=get_client_supplier_repo(),
            supplier_prompt_config_repo=get_supplier_prompt_config_repo(),
            finalization_stage_store=get_finalization_stage_store(),
            artifact_manifest_store=get_artifact_manifest_store(),
            artifact_publication_outbox_store=get_artifact_publication_outbox_store(),
            artifact_staging_store=get_artifact_staging_store(),
        )
        append_worker_bootstrap_event(
            job_id=job_id,
            execution_id=execution_id or (job.execution_id if job is not None else None),
            event="worker.executor_bootstrap_completed",
            details={},
        )
        if job is not None and job.status in (
            V3JobStatus.STARTING,
            V3JobStatus.RUNNING,
            V3JobStatus.CANCEL_REQUESTED,
        ):
            checkpoint_v3_job_bootstrap(
                job_id=job_id,
                execution_id=execution_id or job.execution_id,
                substep="executor_bootstrap_completed",
            )
        handled = executor.execute(base_path, job_id)
        logger.info(
            "worker dispatch result: job_id=%s dispatch=v3_process_aisle handled=%s",
            job_id,
            handled,
        )
        return handled
    except Exception as e:
        logger.exception("v3 process_aisle attempt failed (will try legacy): job_id=%s", job_id)
        _mark_v3_job_failed(
            job_id,
            str(e),
            execution_id=execution_id,
            substep="executor_bootstrap_failed",
        )
        return False


def _push_success_to_db(
    job_id: str,
    report_json_path: Path,
    report_csv_path: Optional[Path],
    artifacts_dir: str,
) -> None:
    """When DB enabled: load report, set_job_outputs, insert pallet_results, insert events."""
    repos = _db_repos()
    if repos is None:
        return
    jobs_repo, pallet_repo, events_repo = repos
    report_data: Optional[dict] = None
    if report_json_path.exists():
        try:
            with open(report_json_path, encoding="utf-8") as f:
                report_data = json.load(f)
        except Exception as e:
            logger.warning("Could not load report for DB push: %s", e)
    frames_count = None
    gemini_calls = None
    prompt_version = None
    pallets_list: list = []
    metrics: dict = {}
    if report_data:
        frames_count = report_data.get("frames_selected")
        prompt_version = report_data.get("prompt_version")
        metrics = report_data.get("metrics") or {}
        gemini_calls = metrics.get("total_calls")
        # v2.2 only produces v2.1-style reports with "entities"
        # Each entity → one pallet_results row. source_image_id/traceability_status per entity (Epic 3.1.B). traceability_warning not persisted to DB.
        entities = report_data.get("entities") or []
        for ent in entities:
            pallets_list.append(
                {
                    "pallet_id": ent.get("pallet_id") or "",
                    "internal_code": ent.get("internal_code"),
                    "final_quantity": ent.get("final_quantity"),
                    "quantity": ent.get("product_label_quantity"),
                    "source": "gemini",
                    "confidence": ent.get("confidence"),
                    "fallback_used": False,
                    "source_image_id": ent.get("source_image_id"),
                    "traceability_status": ent.get("traceability_status"),
                }
            )

    try:
        jobs_repo.set_job_outputs(
            job_id,
            report_json_path=str(report_json_path) if report_json_path.exists() else None,
            report_csv_path=str(report_csv_path)
            if report_csv_path and report_csv_path.exists()
            else None,
            artifacts_dir=artifacts_dir,
            frames_count_sent=frames_count,
            gemini_calls=gemini_calls,
            prompt_version=prompt_version,
        )
        if pallets_list:
            pallet_repo.insert_pallet_results(job_id, pallets_list)
        events_repo.insert_event(job_id, "FRAMES_SELECTED", {"count": frames_count})
        events_repo.insert_event(job_id, "GEMINI_GLOBAL_CALL", {})
        if metrics.get("fallback_attempts", 0) > 0:
            events_repo.insert_event(
                job_id, "FALLBACK_RUN", {"attempts": metrics.get("fallback_attempts")}
            )
        events_repo.insert_event(job_id, "REPORT_WRITTEN", {"path": str(report_json_path)})
    except Exception as e:
        logger.warning("DB push after success failed: %s", e)


def run_job(base_path: Path, job_id: str, execution_id: str | None = None) -> None:
    """Load job, run hybrid pipeline, update status and output. Try v3 process_aisle first."""
    logger.info("worker run_job start: job_id=%s base_path=%s", job_id, str(base_path))
    if _try_v3_process_aisle(base_path, job_id, execution_id=execution_id):
        logger.info("worker run_job handled by v3 executor: job_id=%s", job_id)
        return
    logger.info("worker run_job fallback to legacy flow: job_id=%s", job_id)
    record = get_job(base_path, job_id)
    if record is None:
        logger.warning(
            "Job %s not found in legacy store (expected if this id is v3-only and v3 dispatch already failed)",
            job_id,
        )
        return
    if record.status != JobStatus.QUEUED:
        logger.warning("Job %s not queued (status=%s), skip", job_id, record.status)
        return

    mode = (record.input.mode or "hybrid").strip()
    if mode == "legacy":
        update_job(
            base_path,
            job_id,
            status=JobStatus.FAILED,
            error="legacy mode has been removed as of v2.2; use mode='hybrid'.",
            progress={"stage": "done", "percent": 100},
        )
        logger.info("Job %s: legacy mode rejected", job_id)
        return

    settings = load_settings()
    job_dir = base_path / job_id
    run_id = "run"
    log = setup_logger(str(job_dir), job_id, run_id, console=False)
    output_path = base_path
    video_path = record.input.video_path
    confidence_threshold = record.input.confidence_threshold

    def progress_cb(stage: str, percent: int) -> None:
        update_job(base_path, job_id, progress={"stage": stage, "percent": percent})

    update_job(
        base_path,
        job_id,
        status=JobStatus.RUNNING,
        progress={"stage": "extract_frames", "percent": 10},
    )
    try:
        pipeline = HybridInventoryPipeline()
        result = pipeline.process_video(
            video_path,
            mode="hybrid",
            settings=settings,
            video_id=job_id,
            output_path=output_path,
            run_id=run_id,
            logger=log,
            confidence_threshold=confidence_threshold,
            progress_callback=progress_cb,
            job_input=record.input,
        )
        if result.exit_code != 0:
            logger.error("Job %s failed: pipeline exited with code %s", job_id, result.exit_code)
            update_job(
                base_path,
                job_id,
                status=JobStatus.FAILED,
                error=f"Pipeline exited with code {result.exit_code}",
                progress={"stage": "done", "percent": 100},
            )
            return
        run_dir = output_path / job_id / run_id
        report_json = run_dir / "hybrid_report.json"
        report_csv = run_dir / "hybrid_report.csv"
        update_job(
            base_path,
            job_id,
            status=JobStatus.SUCCEEDED,
            progress={"stage": "done", "percent": 100},
            output={
                "report_json_path": str(report_json) if report_json.exists() else None,
                "report_csv_path": str(report_csv) if report_csv and report_csv.exists() else None,
                "artifacts_dir": str(job_dir),
            },
            error=None,
        )
        _push_success_to_db(job_id, report_json, report_csv, str(job_dir))
        logger.info("Job %s finished successfully", job_id)
    except Exception as e:
        logger.exception("Job %s failed: %s", job_id, e)
        update_job(
            base_path,
            job_id,
            status=JobStatus.FAILED,
            error=str(e),
            progress={"stage": "done", "percent": 100},
        )
        repos = _db_repos()
        if repos is not None:
            try:
                _, _, events_repo = repos
                events_repo.insert_event(job_id, "ERROR", {"message": str(e)})
            except Exception:
                logger.warning(
                    "Could not insert ERROR job_event after pipeline failure: job_id=%s",
                    job_id,
                    exc_info=True,
                )


def worker_loop(base_path: Path, stop: Optional[Callable[[], bool]] = None) -> None:
    """Poll shared store and process claimed jobs until stop() returns True."""
    idle_sleep_sec = 1.0
    idle_log_every_sec = 30.0
    last_idle_log_ts = 0.0
    logger.info("Worker loop started; polling for queued jobs")
    while True:
        if stop and stop():
            break
        claimed = claim_next_job(base_path)
        if claimed is None:
            now = time.monotonic()
            if now - last_idle_log_ts >= idle_log_every_sec:
                logger.info("Worker poll idle: no queued jobs available")
                last_idle_log_ts = now
            time.sleep(idle_sleep_sec)
            continue
        logger.info(
            "Worker claimed job %s (job_type=%s target_type=%s target_id=%s inventory_id=%s aisle_id=%s status=%s)",
            claimed.job_id,
            ((claimed.input.metadata or {}).get("job_type") if claimed.input else None)
            or "process_aisle",
            ((claimed.input.metadata or {}).get("target_type") if claimed.input else None)
            or "aisle",
            ((claimed.input.metadata or {}).get("target_id") if claimed.input else None)
            or ((claimed.input.metadata or {}).get("aisle_id")),
            (claimed.input.metadata or {}).get("inventory_id") if claimed.input else None,
            (claimed.input.metadata or {}).get("aisle_id") if claimed.input else None,
            claimed.status.value if hasattr(claimed.status, "value") else str(claimed.status),
        )
        run_job(base_path, claimed.job_id)
