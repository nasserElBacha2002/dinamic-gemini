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
    JobRepository,
    PositionRepository,
    ProductRecordRepository,
    SourceAssetRepository,
)
from src.application.use_cases.persist_aisle_result import (
    PersistAisleResultCommand,
    PersistAisleResultUseCase,
)
from src.config import load_settings
from src.domain.aisle.entities import Aisle
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.jobs.entities import Job, JobStatus
from src.io.logging import setup_logger
from src.jobs.models import JobInput
from src.pipeline.hybrid_inventory_pipeline import HybridInventoryPipeline

logger = logging.getLogger(__name__)

RUN_ID = "run"


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
    ) -> None:
        self._job_repo = job_repo
        self._aisle_repo = aisle_repo
        self._source_asset_repo = source_asset_repo
        self._position_repo = position_repo
        self._product_record_repo = product_record_repo
        self._evidence_repo = evidence_repo
        self._clock = clock
        self._persist_use_case = PersistAisleResultUseCase(
            position_repo=position_repo,
            product_record_repo=product_record_repo,
            evidence_repo=evidence_repo,
            clock=clock,
        )

    def execute(self, base_path: Path, job_id: str) -> bool:
        """
        If job_id is a v3 process_aisle job: load aisle/assets, run pipeline, persist, update status; return True.
        Otherwise return False (caller may run legacy flow).
        """
        job = self._job_repo.get_by_id(job_id)
        if job is None or job.job_type != "process_aisle":
            return False
        if job.status != JobStatus.QUEUED:
            logger.warning("v3 job %s not queued (status=%s), skip", job_id, job.status.value)
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

        assets = list(self._source_asset_repo.list_by_aisle(aisle_id))
        if not assets:
            self._fail_job_and_aisle(job_id, aisle, "No source assets for aisle")
            return True

        now = self._clock.now()
        self._mark_running(job_id, aisle, now)

        settings = load_settings()
        output_dir = Path(settings.output_dir)
        v3_base = output_dir / "v3_uploads"
        job_dir = base_path / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        try:
            job_input, video_path = self._build_pipeline_input(
                assets, v3_base, job_dir, job_id
            )
        except Exception as e:
            logger.exception("v3 job %s: build pipeline input failed: %s", job_id, e)
            self._fail_job_and_aisle(job_id, aisle, str(e))
            return True

        run_dir = base_path / job_id / RUN_ID
        log = setup_logger(str(job_dir), job_id, RUN_ID, console=False)

        try:
            pipeline = HybridInventoryPipeline()
            code = pipeline.process_video(
                video_path,
                mode="hybrid",
                settings=settings,
                video_id=job_id,
                output_path=base_path,
                run_id=RUN_ID,
                logger=log,
                progress_callback=None,
                job_input=job_input,
            )
            if code != 0:
                self._fail_job_and_aisle(
                    job_id, aisle, f"Pipeline exited with code {code}"
                )
                return True

            report_path = run_dir / "hybrid_report.json"
            if not report_path.exists():
                self._fail_job_and_aisle(
                    job_id, aisle, "Pipeline did not produce hybrid_report.json"
                )
                return True

            with open(report_path, encoding="utf-8") as f:
                report = json.load(f)

            self._persist_use_case.execute(
                PersistAisleResultCommand(
                    aisle_id=aisle_id,
                    job_id=job_id,
                    report=report,
                    run_dir=run_dir,
                    run_id=RUN_ID,
                )
            )

            self._mark_success(job_id, aisle, report_path, now)
        except Exception as e:
            logger.exception("v3 job %s failed: %s", job_id, e)
            self._fail_job_and_aisle(job_id, aisle, str(e))

        return True

    def _build_pipeline_input(
        self,
        assets: list,
        v3_base: Path,
        job_dir: Path,
        job_id: str,
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
            return (
                JobInput(
                    video_path=video_path,
                    mode="hybrid",
                    input_type="video",
                ),
                video_path,
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
            photos_list.append({"index": i, "stored_filename": stored})

        manifest_path = job_dir / "input_manifest.json"
        manifest = {
            "input_type": "photos",
            "photos": photos_list,
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        # Paths relative to job dir for pipeline
        return (
            JobInput(
                video_path="",
                mode="hybrid",
                input_type="photos",
                input_manifest_path="input_manifest.json",
                photos_dir="input_photos",
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

    def _mark_success(
        self, job_id: str, aisle: Aisle, report_path: Path, now
    ) -> None:
        job = self._job_repo.get_by_id(job_id)
        if job:
            job.status = JobStatus.SUCCEEDED
            job.updated_at = now
            job.result_json = {"report_path": str(report_path)}
            job.error_message = None
            self._job_repo.save(job)
        aisle.mark_processed(now)
        self._aisle_repo.save(aisle)

    def _fail_job(self, job_id: str, error_message: str) -> None:
        job = self._job_repo.get_by_id(job_id)
        if job:
            now = self._clock.now()
            job.status = JobStatus.FAILED
            job.updated_at = now
            job.error_message = error_message[:2048] if len(error_message) > 2048 else error_message
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
