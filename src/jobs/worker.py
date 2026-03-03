"""Stage 7 — Background worker: pull jobs from queue and run inventory engine."""

import logging
from pathlib import Path
from typing import Any, Callable, Optional

from src.config import load_settings
from src.jobs.models import JobRecord, JobStatus
from src.jobs.job_store import get_job, update_job
from src.jobs.queue import dequeue
from src.io.logging import setup_logger
from src.pipeline.hybrid_inventory_pipeline import HybridInventoryPipeline

logger = logging.getLogger(__name__)


def _make_fake_args() -> Any:
    """Minimal args namespace for legacy pipeline (all defaults)."""
    class Args:
        track_pipeline = False
        synthetic = False
        heuristic = False
        reid_enabled = False
        debug_view_selection = False
        extract_fps = None
        prompt_profile = "multi_frame_consolidated"
        debug = False
        save_annotated = False
        no_summary = True
        frame_stride = None
        max_frames = None
        time_limit_sec = None
        filter_similar = False
        similarity_threshold = 0.95
        strategy = "all"
        resize_max_side = None
        raw_gemini = False
    return Args()


def run_job(base_path: Path, job_id: str) -> None:
    """Load job, run engine (legacy or hybrid), update status and output."""
    record = get_job(base_path, job_id)
    if record is None:
        logger.warning("Job %s not found", job_id)
        return
    if record.status != JobStatus.QUEUED:
        logger.warning("Job %s not queued (status=%s), skip", job_id, record.status)
        return

    settings = load_settings()
    job_dir = base_path / job_id
    run_id = "run"
    log = setup_logger(str(job_dir), job_id, run_id, console=False)
    output_path = base_path
    video_path = record.input.video_path
    mode = record.input.mode or "legacy"
    confidence_threshold = record.input.confidence_threshold

    def progress_cb(stage: str, percent: int) -> None:
        update_job(base_path, job_id, progress={"stage": stage, "percent": percent})

    update_job(base_path, job_id, status=JobStatus.RUNNING, progress={"stage": "extract_frames", "percent": 10})
    try:
        pipeline = HybridInventoryPipeline()
        if mode == "legacy":
            code = pipeline.legacy_pipeline.run(
                video_path,
                settings=settings,
                video_id=job_id,
                output_path=output_path,
                run_id=run_id,
                logger=log,
                args=_make_fake_args(),
            )
        else:
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
        if mode == "legacy":
            report_json = run_dir / "result.json"
            report_csv = None
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
    except Exception as e:
        logger.exception("Job %s failed: %s", job_id, e)
        update_job(
            base_path,
            job_id,
            status=JobStatus.FAILED,
            error=str(e),
            progress={"stage": "done", "percent": 100},
        )


def worker_loop(base_path: Path, stop: Optional[Callable[[], bool]] = None) -> None:
    """Consume queue until stop() returns True."""
    while True:
        if stop and stop():
            break
        job_id = dequeue(timeout=1.0)
        if job_id:
            run_job(base_path, job_id)
