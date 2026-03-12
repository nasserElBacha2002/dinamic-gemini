"""
Hybrid inventory pipeline (v2.1).
Stage 2.2.B: frames via FrameSource; v2.3.A: RunContext, InputPreparationStage; v2.3.B: AnalysisProvider; v2.3.C: staged orchestration.
"""

from pathlib import Path
from typing import Any, Callable, Optional

import cv2
import numpy as np

from src.config import Settings
from src.jobs.models import JobInput
from src.llm.errors import LLMProviderError
from src.parsing.global_analysis_parser import GlobalAnalysisParseError
from src.pipeline.context.run_context import RunContext
from src.pipeline.execution_log import ExecutionLogWriter
from src.pipeline.ports.analysis_provider import AnalysisProvider
from src.pipeline.adapters.gemini_analysis_provider import GeminiAnalysisProvider
from src.pipeline.stages.input_preparation_stage import InputPreparationStage, PreparedInput
from src.pipeline.stages.frame_acquisition_stage import FrameAcquisitionStage, AcquiredFrames
from src.pipeline.stages.analysis_stage import AnalysisStage
from src.pipeline.stages.entity_resolution_stage import EntityResolutionStage
from src.pipeline.stages.evidence_stage import EvidenceStage, EvidenceStageInput
from src.pipeline.stages.reporting_stage import ReportingStage, ReportingStageInput

# Default max frames when hybrid_max_frames is None (kept for test imports)
HYBRID_MAX_FRAMES = 10000


def _save_frames_sent_to_gemini(
    run_dir: Path,
    frames: list,
    frame_indices: Optional[list] = None,
) -> None:
    """Save the frames that were sent to Gemini as JPGs under run_dir/frames_sent/ (when DEBUG_SAVE_FRAMES=true)."""
    if not frames:
        return
    out_dir = run_dir / "frames_sent"
    out_dir.mkdir(parents=True, exist_ok=True)
    indices = frame_indices if frame_indices is not None and len(frame_indices) == len(frames) else list(range(len(frames)))
    for i, (frame, idx) in enumerate(zip(frames, indices)):
        path = out_dir / f"frame_{idx:06d}.jpg"
        if not cv2.imwrite(str(path), frame):
            path = out_dir / f"frame_{i:04d}.jpg"
            cv2.imwrite(str(path), frame)


class HybridInventoryPipeline:
    """Staged hybrid flow: InputPreparation → FrameAcquisition → Analysis → EntityResolution → Evidence → Reporting."""

    def __init__(self, analysis_provider: Optional[AnalysisProvider] = None) -> None:
        """Optional analysis_provider; when None, uses GeminiAnalysisProvider (current behavior)."""
        self._analysis_provider: AnalysisProvider = (
            analysis_provider if analysis_provider is not None else GeminiAnalysisProvider()
        )
        self._input_stage = InputPreparationStage()
        self._frame_acquisition_stage = FrameAcquisitionStage()
        self._analysis_stage = AnalysisStage(self._analysis_provider)
        self._entity_resolution_stage = EntityResolutionStage()
        self._evidence_stage = EvidenceStage()
        self._reporting_stage = ReportingStage()

    def process_video(
        self,
        video_path: str,
        mode: str = "hybrid",
        **kwargs: object,
    ) -> int:
        if mode != "hybrid":
            raise ValueError(f"Invalid mode: {mode!r}; only 'hybrid' is supported as of v2.2.")
        return self._run_hybrid(video_path, **kwargs)

    def _run_hybrid(
        self,
        video_path: str,
        *,
        settings: Settings,
        video_id: str,
        output_path: Path,
        run_id: str,
        logger: Any,
        confidence_threshold: Optional[float] = None,
        progress_callback: Optional[Callable[[str, int], None]] = None,
        job_input: Optional[JobInput] = None,
        **_: object,
    ) -> int:
        """Orchestrate staged pipeline; preserve exit codes and progress semantics."""
        execution_id = video_id
        if job_input is None:
            job_input = JobInput(video_path=video_path or "", mode="hybrid", input_type="video")
        workspace_path = output_path
        run_dir = output_path / execution_id / run_id
        context = RunContext(
            job_id=execution_id,
            run_id=run_id,
            workspace_path=workspace_path,
            run_dir=run_dir,
            job_input=job_input,
            settings=settings,
            logger=logger,
            progress_callback=progress_callback,
            metadata={},
        )
        run_dir.mkdir(parents=True, exist_ok=True)
        exec_log = ExecutionLogWriter(run_dir)
        context.execution_log = exec_log

        progress_cb = progress_callback

        def _report(stage: str, percent: int) -> None:
            if callable(progress_cb):
                try:
                    progress_cb(stage, percent)
                except Exception:
                    pass

        def _fail(stage: str, e: BaseException) -> int:
            msg = str(e).strip() or repr(e)
            exec_log.error(stage, f"{stage} failed: {msg}", payload={"error": msg[:500]})
            exec_log.write_last_stage_error(stage, msg)
            logger.exception("Stage failure: %s (job_id=%s): %s", stage, context.job_id, e)
            return 1

        exec_log.info("Pipeline", "Job started", payload={"job_id": execution_id})
        try:
            exec_log.info("InputPreparationStage", "Input preparation started")
            prepared: PreparedInput = self._input_stage.run(context, None)
            exec_log.info("InputPreparationStage", "Input preparation completed")
        except (FileNotFoundError, ValueError) as e:
            return _fail("InputPreparationStage", e)

        _report("extract_frames", 10)
        try:
            exec_log.info("FrameAcquisitionStage", "Frame acquisition started")
            acquired: AcquiredFrames = self._frame_acquisition_stage.run(context, prepared)
            exec_log.info("FrameAcquisitionStage", "Frame acquisition completed", payload={"frames": len(acquired.frames_nd)})
        except (ValueError, FileNotFoundError, RuntimeError) as e:
            return _fail("FrameAcquisitionStage", e)

        _report("gemini_global_call", 50)
        try:
            exec_log.info("AnalysisStage", "Gemini/LLM analysis started")
            analysis_result = self._analysis_stage.run(context, acquired)
            exec_log.info("AnalysisStage", "Gemini/LLM analysis succeeded")
        except LLMProviderError as e:
            exec_log.error("AnalysisStage", f"Gemini/LLM analysis failed: {e}", payload={"error": str(e)[:500]})
            exec_log.write_last_stage_error("AnalysisStage", str(e))
            logger.exception("Stage failure: AnalysisStage (job_id=%s): %s", context.job_id, e)
            return 1

        try:
            exec_log.info("EntityResolutionStage", "Entity resolution started")
            resolved = self._entity_resolution_stage.run(context, analysis_result)
            exec_log.info("EntityResolutionStage", "Entity resolution completed")
        except GlobalAnalysisParseError as e:
            return _fail("EntityResolutionStage", e)

        _report("evidence_pack", 85)
        try:
            exec_log.info("EvidenceStage", "Evidence generation started")
            evidence_input = EvidenceStageInput(
                entities=resolved.entities,
                frames_nd=acquired.frames_nd,
                metadata=acquired.metadata,
            )
            self._evidence_stage.run(context, evidence_input)
            exec_log.info("EvidenceStage", "Evidence generation completed")
        except Exception as e:
            return _fail("EvidenceStage", e)

        video_path_for_report = video_path or (
            f"photos_{video_id}" if prepared.job_input.input_type == "photos" else ""
        )
        reporting_input = ReportingStageInput(
            entities=resolved.entities,
            frames_count=len(acquired.frames_nd),
            frame_indices=acquired.metadata.get("frame_indices"),
            video_path_for_report=video_path_for_report,
        )
        _report("write_artifacts", 90)
        if getattr(settings, "debug_save_frames", False):
            _save_frames_sent_to_gemini(context.run_dir, acquired.frames_nd, acquired.metadata.get("frame_indices"))
        try:
            exec_log.info("ReportingStage", "Reporting started")
            self._reporting_stage.run(context, reporting_input)
            exec_log.info("ReportingStage", "Reporting completed")
        except Exception as e:
            return _fail("ReportingStage", e)
        exec_log.info("Pipeline", "Job completed successfully")
        _report("done", 100)
        return 0
