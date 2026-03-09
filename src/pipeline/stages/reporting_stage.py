"""
ReportingStage — assemble report payload and write hybrid_report.json (v2.3.C).

Preserves current report schema and artifact path; does not change top-level keys or version.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.domain.entity import Entity
from src.reporting.artifacts import write_json
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
    """Stage: build hybrid report dict and write hybrid_report.json to run_dir."""

    def run(self, context: RunContext, data: ReportingStageInput) -> ReportingResult:
        """Assemble report with current structure; write to context.run_dir / hybrid_report.json."""
        run_dir = context.run_dir
        logger = context.logger

        report = build_hybrid_report(
            video_path=data.video_path_for_report,
            entities=data.entities,
            frames_selected=data.frames_count,
            frame_indices=data.frame_indices,
        )
        report_path = run_dir / "hybrid_report.json"
        write_json(report_path, report)
        logger.info("Reporte hybrid v2.1 guardado: %s", report_path)
        return ReportingResult(report_path=report_path, report=report)
