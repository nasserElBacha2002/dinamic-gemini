"""Stage 7 — Background worker: pull jobs from queue and run inventory engine.
Stage 8 — When SQL Server enabled, push status/progress/outputs/pallet_results/events to DB.
Épica 6 — Try v3 process_aisle job first; fall back to legacy job record.
"""

import json
import logging
from pathlib import Path
from typing import Any, Callable, Optional

from src.config import load_settings
from src.jobs.job_store import _db_repos, get_job, update_job
from src.jobs.models import JobStatus
from src.jobs.queue import dequeue
from src.io.logging import setup_logger
from src.pipeline.hybrid_inventory_pipeline import HybridInventoryPipeline

logger = logging.getLogger(__name__)


def _try_v3_process_aisle(base_path: Path, job_id: str) -> bool:
    """If job_id is a v3 process_aisle job, run it and return True. Otherwise return False."""
    try:
        from src.runtime.v3_deps import (
            get_aisle_repo,
            get_clock,
            get_evidence_repo,
            get_job_repo,
            get_position_repo,
            get_product_record_repo,
            get_source_asset_repo,
        )
        from src.infrastructure.pipeline.v3_job_executor import V3JobExecutor

        executor = V3JobExecutor(
            job_repo=get_job_repo(),
            aisle_repo=get_aisle_repo(),
            source_asset_repo=get_source_asset_repo(),
            position_repo=get_position_repo(),
            product_record_repo=get_product_record_repo(),
            evidence_repo=get_evidence_repo(),
            clock=get_clock(),
        )
        return executor.execute(base_path, job_id)
    except Exception as e:
        logger.warning("v3 process_aisle attempt failed (will try legacy): %s", e)
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
        entities = report_data.get("entities") or []
        for ent in entities:
            pallets_list.append({
                "pallet_id": ent.get("pallet_id") or "",
                "internal_code": ent.get("internal_code"),
                "final_quantity": ent.get("final_quantity"),
                "quantity": ent.get("product_label_quantity"),
                "source": "gemini",
                "confidence": ent.get("confidence"),
                "fallback_used": False,
            })

    try:
        jobs_repo.set_job_outputs(
            job_id,
            report_json_path=str(report_json_path) if report_json_path.exists() else None,
            report_csv_path=str(report_csv_path) if report_csv_path and report_csv_path.exists() else None,
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
            events_repo.insert_event(job_id, "FALLBACK_RUN", {"attempts": metrics.get("fallback_attempts")})
        events_repo.insert_event(job_id, "REPORT_WRITTEN", {"path": str(report_json_path)})
    except Exception as e:
        logger.warning("DB push after success failed: %s", e)


def run_job(base_path: Path, job_id: str) -> None:
    """Load job, run hybrid pipeline, update status and output. Try v3 process_aisle first."""
    if _try_v3_process_aisle(base_path, job_id):
        return
    record = get_job(base_path, job_id)
    if record is None:
        logger.warning("Job %s not found", job_id)
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

    update_job(base_path, job_id, status=JobStatus.RUNNING, progress={"stage": "extract_frames", "percent": 10})
    try:
        pipeline = HybridInventoryPipeline()
        code = pipeline.process_video(
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
        if code != 0:
            update_job(
                base_path,
                job_id,
                status=JobStatus.FAILED,
                error=f"Pipeline exited with code {code}",
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
                pass


def worker_loop(base_path: Path, stop: Optional[Callable[[], bool]] = None) -> None:
    """Consume queue until stop() returns True."""
    while True:
        if stop and stop():
            break
        job_id = dequeue(timeout=1.0)
        if job_id:
            run_job(base_path, job_id)
