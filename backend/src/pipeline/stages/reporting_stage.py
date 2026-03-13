"""
ReportingStage — assemble report payload and write hybrid_report.json (v2.3.C).
Epic 3.1.C: also write hybrid_report.csv (entity-based with traceability columns).
CSV is always generated for this pipeline (no feature flag); artifact set is fixed.

Epic 5: For photos jobs only, we build image_id -> original_filename from the manifest and pass
it to build_hybrid_report so entity dicts get source_image_original_filename. Video jobs do not
receive a map; the field is then null/absent. Legacy reports (pre-Epic 5) do not contain the field;
the API and CSV handle absence by returning null or empty string.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.domain.entity import Entity
from src.jobs.image_identity import load_job_images_from_manifest
from src.jobs.photos_paths import photos_dir_relative_for_manifest, resolve_manifest_path
from src.reporting.artifacts import write_json, write_report_csv
from src.reporting.hybrid_report import build_hybrid_report
from src.pipeline.context.run_context import RunContext


@dataclass
class ReportingStageInput:
    """Input for ReportingStage: resolved entities plus frame count and metadata (orchestrator assembles)."""

    entities: List[Entity]
    frames_count: int
    frame_indices: Optional[List[int]]
    video_path_for_report: str  # video_path or photos_{job_id}


@dataclass
class ReportingResult:
    """Output of ReportingStage: path and payload written."""

    report_path: Path
    report: Dict[str, Any]


class ReportingStage:
    """Stage: build hybrid report dict and write hybrid_report.json and hybrid_report.csv to run_dir. CSV is always generated (Epic 3.1.C)."""

    def run(self, context: RunContext, data: ReportingStageInput) -> ReportingResult:
        """Assemble report with current structure; write to context.run_dir / hybrid_report.json."""
        run_dir = context.run_dir
        logger = context.logger

        # Epic 5: for photos jobs, build image_id -> original_filename so report/export expose source_image_original_filename.
        # Uses public path helpers (no dependency on private frame-source helpers).
        source_image_filename_map: Optional[Dict[str, str]] = None
        job_input = getattr(context, "job_input", None)
        if job_input and getattr(job_input, "input_type", "") == "photos":
            manifest_path = resolve_manifest_path(run_dir, job_input)
            photos_dir_rel = photos_dir_relative_for_manifest(job_input)
            job_images = load_job_images_from_manifest(manifest_path, photos_dir_rel)
            source_image_filename_map = {img.image_id: img.original_filename for img in job_images}

        report = build_hybrid_report(
            video_path=data.video_path_for_report,
            entities=data.entities,
            frames_selected=data.frames_count,
            frame_indices=data.frame_indices,
            source_image_filename_map=source_image_filename_map,
        )
        report_path = run_dir / "hybrid_report.json"
        write_json(report_path, report)
        csv_path = run_dir / "hybrid_report.csv"
        write_report_csv(csv_path, report)
        logger.info("Reporte hybrid v2.1 guardado: %s", report_path)
        logger.info("Epic 3.1.C: hybrid_report.csv written (always generated for this pipeline).")
        return ReportingResult(report_path=report_path, report=report)
