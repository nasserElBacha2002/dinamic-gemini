"""
Hybrid inventory pipeline (v2.1).
Stage 2.2.B: frames via FrameSource; v2.3.A: RunContext, InputPreparationStage; v2.3.B: AnalysisProvider; v2.3.C: staged orchestration.
v3.2.4 Phase 5: produce run_metadata in memory (visual_reference_context) for job-level traceability.
"""

import json
from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any, Callable, Dict, Optional

import cv2
import numpy as np

from src.config import Settings
from src.jobs.models import JobInput
from src.llm.errors import LLMProviderError
from src.parsing.global_analysis_parser import GlobalAnalysisParseError
from src.pipeline.context.run_context import RunContext
from src.pipeline.errors import PipelineCancellationRequestedError
from src.pipeline.contracts.analysis_context import AnalysisContext, analysis_context_from_dict
from src.pipeline.execution_log import ExecutionLogWriter
from src.pipeline.ports.analysis_provider import AnalysisProvider
from src.pipeline.providers.registry import default_analysis_provider
from src.pipeline.stages.input_preparation_stage import InputPreparationStage, PreparedInput
from src.pipeline.stages.frame_acquisition_stage import FrameAcquisitionStage, AcquiredFrames
from src.pipeline.stages.analysis_stage import AnalysisStage
from src.pipeline.stages.entity_resolution_stage import EntityResolutionStage
from src.pipeline.stages.evidence_stage import EvidenceStage, EvidenceStageInput
from src.pipeline.stages.reporting_stage import ReportingStage, ReportingStageInput
from src.pipeline.run_metadata import (
    RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT,
    build_run_metadata,
)


@dataclass
class PipelineRunResult:
    """Result of a pipeline run. Phase 5: run_metadata propagated in memory for job persistence."""

    exit_code: int
    run_metadata: Optional[Dict[str, Any]] = None

# Default max frames when hybrid_max_frames is None (kept for test imports)
HYBRID_MAX_FRAMES = 10000


def _save_frames_sent_to_llm(
    run_dir: Path,
    frames: list,
    frame_indices: Optional[list] = None,
) -> None:
    """Save frames sent to the analysis provider under run_dir/frames_sent/ (when DEBUG_SAVE_FRAMES=true)."""
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
        """Optional analysis_provider; when None, uses ``default_analysis_provider()`` (``HybridGlobalAnalysisStrategy``)."""
        self._analysis_provider: AnalysisProvider = (
            analysis_provider if analysis_provider is not None else default_analysis_provider()
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
    ) -> PipelineRunResult:
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
        analysis_context: Optional[AnalysisContext] = None,
        execution_observer=None,
        pipeline_provider_name: Optional[str] = None,
        job_model_name: Optional[str] = None,
        job_prompt_key: Optional[str] = None,
        cancellation_checkpoint: Any = None,
        **_: object,
    ) -> PipelineRunResult:
        """Orchestrate staged pipeline; return result with exit code and run_metadata (Phase 5)."""
        execution_id = video_id
        if job_input is None:
            job_input = JobInput(video_path=video_path or "", mode="hybrid", input_type="video")
        workspace_path = output_path
        run_dir = output_path / execution_id / run_id
        # Phase 3/4/5: prefer typed AnalysisContext passed in-memory by orchestrator.
        # Compatibility fallback: parse from job_input.metadata['analysis_context'] if present.
        if analysis_context is None:
            raw_ctx = (getattr(job_input, "metadata", None) or {}).get("analysis_context")
            analysis_context = analysis_context_from_dict(raw_ctx) if isinstance(raw_ctx, dict) else None
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
            analysis_context=analysis_context,
            execution_observer=execution_observer,
            cancellation_checkpoint=cancellation_checkpoint,
            pipeline_provider_name=pipeline_provider_name,
            job_model_name=job_model_name,
            job_prompt_key=job_prompt_key,
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

        def _fail(stage: str, e: BaseException) -> PipelineRunResult:
            msg = str(e).strip() or repr(e)
            exec_log.error(stage, f"{stage} failed: {msg}", payload={"error": msg[:500]})
            context.emit_stage_event(
                stage=stage,
                event="stage.failed",
                details={"error": msg[:500]},
                level="error",
            )
            exec_log.write_last_stage_error(stage, msg)
            logger.exception("Stage failure: %s (job_id=%s): %s", stage, context.job_id, e)
            return PipelineRunResult(exit_code=1, run_metadata=None)

        exec_log.info("Pipeline", "Job started", payload={"job_id": execution_id})
        context.emit_stage_event(stage="Pipeline", event="job.started")
        try:
            context.check_cancellation(stage="InputPreparationStage", reason="Job canceled before input preparation")
            stage_started = time.monotonic()
            exec_log.info("InputPreparationStage", "Input preparation started")
            context.emit_stage_event(stage="InputPreparationStage", event="stage.started")
            prepared: PreparedInput = self._input_stage.run(context, None)
            duration_ms = int((time.monotonic() - stage_started) * 1000)
            exec_log.info("InputPreparationStage", "Input preparation completed")
            context.emit_stage_event(
                stage="InputPreparationStage",
                event="stage.completed",
                duration_ms=duration_ms,
            )
        except PipelineCancellationRequestedError:
            raise
        except (FileNotFoundError, ValueError) as e:
            return _fail("InputPreparationStage", e)

        _report("extract_frames", 10)
        try:
            context.check_cancellation(stage="FrameAcquisitionStage", reason="Job canceled before frame acquisition")
            stage_started = time.monotonic()
            exec_log.info("FrameAcquisitionStage", "Frame acquisition started")
            context.emit_stage_event(stage="FrameAcquisitionStage", event="stage.started")
            acquired: AcquiredFrames = self._frame_acquisition_stage.run(context, prepared)
            duration_ms = int((time.monotonic() - stage_started) * 1000)
            exec_log.info("FrameAcquisitionStage", "Frame acquisition completed", payload={"frames": len(acquired.frames_nd)})
            context.emit_stage_event(
                stage="FrameAcquisitionStage",
                event="stage.completed",
                details={"frames": len(acquired.frames_nd)},
                duration_ms=duration_ms,
            )
        except PipelineCancellationRequestedError:
            raise
        except (ValueError, FileNotFoundError, RuntimeError) as e:
            return _fail("FrameAcquisitionStage", e)

        _report("global_analysis_call", 50)
        try:
            context.check_cancellation(stage="AnalysisStage", reason="Job canceled before analysis")
            stage_started = time.monotonic()
            exec_log.info("AnalysisStage", "LLM analysis started")
            context.emit_stage_event(stage="AnalysisStage", event="stage.started")
            analysis_result = self._analysis_stage.run(context, acquired)
            duration_ms = int((time.monotonic() - stage_started) * 1000)
            exec_log.info("AnalysisStage", "LLM analysis succeeded")
            context.emit_stage_event(stage="AnalysisStage", event="stage.completed", duration_ms=duration_ms)
        except PipelineCancellationRequestedError:
            raise
        except LLMProviderError as e:
            exec_log.error("AnalysisStage", f"LLM analysis failed: {e}", payload={"error": str(e)[:500]})
            context.emit_stage_event(
                stage="AnalysisStage",
                event="stage.failed",
                details={"error": str(e)[:500]},
                level="error",
            )
            exec_log.write_last_stage_error("AnalysisStage", str(e))
            logger.exception("Stage failure: AnalysisStage (job_id=%s): %s", context.job_id, e)
            return PipelineRunResult(exit_code=1, run_metadata=None)

        try:
            context.check_cancellation(stage="EntityResolutionStage", reason="Job canceled before entity resolution")
            stage_started = time.monotonic()
            exec_log.info("EntityResolutionStage", "Entity resolution started")
            context.emit_stage_event(stage="EntityResolutionStage", event="stage.started")
            resolved = self._entity_resolution_stage.run(context, analysis_result)
            duration_ms = int((time.monotonic() - stage_started) * 1000)
            exec_log.info("EntityResolutionStage", "Entity resolution completed")
            context.emit_stage_event(
                stage="EntityResolutionStage",
                event="stage.completed",
                duration_ms=duration_ms,
            )
        except PipelineCancellationRequestedError:
            raise
        except GlobalAnalysisParseError as e:
            return _fail("EntityResolutionStage", e)

        _report("evidence_pack", 85)
        try:
            context.check_cancellation(stage="EvidenceStage", reason="Job canceled before evidence generation")
            stage_started = time.monotonic()
            exec_log.info("EvidenceStage", "Evidence generation started")
            context.emit_stage_event(stage="EvidenceStage", event="stage.started")
            evidence_input = EvidenceStageInput(
                entities=resolved.entities,
                frames_nd=acquired.frames_nd,
                metadata=acquired.metadata,
            )
            self._evidence_stage.run(context, evidence_input)
            duration_ms = int((time.monotonic() - stage_started) * 1000)
            exec_log.info("EvidenceStage", "Evidence generation completed")
            context.emit_stage_event(stage="EvidenceStage", event="stage.completed", duration_ms=duration_ms)
        except PipelineCancellationRequestedError:
            raise
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
            _save_frames_sent_to_llm(context.run_dir, acquired.frames_nd, acquired.metadata.get("frame_indices"))
        try:
            context.check_cancellation(stage="ReportingStage", reason="Job canceled before reporting")
            stage_started = time.monotonic()
            exec_log.info("ReportingStage", "Reporting started")
            context.emit_stage_event(stage="ReportingStage", event="stage.started")
            self._reporting_stage.run(context, reporting_input)
            duration_ms = int((time.monotonic() - stage_started) * 1000)
            exec_log.info("ReportingStage", "Reporting completed")
            context.emit_stage_event(stage="ReportingStage", event="stage.completed", duration_ms=duration_ms)
        except PipelineCancellationRequestedError:
            raise
        except Exception as e:
            return _fail("ReportingStage", e)
        # Phase 5: build run_metadata in memory (formal AnalysisContext); optional file as debug artifact
        run_metadata = build_run_metadata(context.analysis_context, analysis_result.provider_metadata)
        # Phase 7: run attribution for debugging (provider and prompt_key persisted in job.result_json)
        provider = (analysis_result.provider_name or "").strip() or None
        run_metadata["provider"] = provider
        prompt_key = getattr(context, "job_prompt_key", None) or getattr(settings, "hybrid_prompt", None)
        if prompt_key is not None and str(prompt_key).strip():
            pk = str(prompt_key).strip()
            run_metadata["prompt_key"] = pk
            # Traceability: prompt profile key + hybrid report schema tag (see LLMRequest.schema_version).
            run_metadata["prompt_version"] = f"{pk}@v2.1"
        if getattr(settings, "debug_run_metadata", False):
            try:
                (context.run_dir / "run_metadata.json").write_text(
                    json.dumps(run_metadata, indent=2), encoding="utf-8"
                )
            except OSError as e:
                logger.warning("Failed to write run_metadata.json (job_id=%s): %s", context.job_id, e)
        exec_log.info("Pipeline", "Job completed successfully")
        context.emit_stage_event(stage="Pipeline", event="job.succeeded")
        _report("done", 100)
        return PipelineRunResult(exit_code=0, run_metadata=run_metadata)
