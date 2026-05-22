"""
Hybrid inventory pipeline (v2.1).
Stage 2.2.B: frames via FrameSource; v2.3.A: RunContext, InputPreparationStage; v2.3.B: AnalysisProvider; v2.3.C: staged orchestration.
v3.2.4 Phase 5: produce run_metadata in memory (visual_reference_context) for job-level traceability.
"""

import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, Union

import cv2

from src.application.services.run_audit_snapshot import build_run_audit_snapshot
from src.application.services.supplier_prompt_resolver import SupplierPromptResolution
from src.config import Settings
from src.jobs.models import JobInput
from src.llm.errors import LLMProviderError
from src.parsing.global_analysis_parser import GlobalAnalysisParseError
from src.pipeline.context.run_context import RunContext
from src.pipeline.contracts.analysis_context import AnalysisContext, analysis_context_from_dict
from src.pipeline.errors import PipelineCancellationRequestedError
from src.pipeline.execution_log import ExecutionLogWriter
from src.pipeline.ports.analysis_provider import AnalysisProvider
from src.pipeline.providers.registry import default_analysis_provider
from src.pipeline.run_metadata import (
    RUN_METADATA_KEY_RUN_AUDIT_SNAPSHOT,
    build_run_metadata,
)
from src.pipeline.stages.analysis_stage import AnalysisStage, AnalysisStageResult
from src.pipeline.stages.entity_resolution_stage import EntityResolutionStage, ResolvedEntities
from src.pipeline.stages.evidence_stage import EvidenceStage, EvidenceStageInput
from src.pipeline.stages.frame_acquisition_stage import AcquiredFrames, FrameAcquisitionStage
from src.pipeline.stages.input_preparation_stage import InputPreparationStage, PreparedInput
from src.pipeline.stages.reporting_stage import ReportingStage, ReportingStageInput


@dataclass
class PipelineRunResult:
    """Result of a pipeline run. Phase 5: run_metadata propagated in memory for job persistence."""

    exit_code: int
    run_metadata: Optional[dict[str, Any]] = None


# Default max frames when hybrid_max_frames is None (kept for test imports)
HYBRID_MAX_FRAMES = 10000

_REQUIRED_HYBRID_KWARGS: tuple[str, ...] = (
    "settings",
    "video_id",
    "output_path",
    "run_id",
    "logger",
)


@dataclass(frozen=True)
class _HybridRunParams:
    """Internal keyword bundle for :meth:`HybridInventoryPipeline._run_hybrid` (B8.3: PLR0913)."""

    settings: Settings
    video_id: str
    output_path: Path
    run_id: str
    logger: Any
    confidence_threshold: Optional[float] = None
    progress_callback: Optional[Callable[[str, int], None]] = None
    job_input: Optional[JobInput] = None
    analysis_context: Optional[AnalysisContext] = None
    execution_observer: Any = None
    pipeline_provider_name: Optional[str] = None
    job_model_name: Optional[str] = None
    job_prompt_key: Optional[str] = None
    job_prompt_version: Optional[str] = None
    job_prompt_parity_mode: bool = False
    cancellation_checkpoint: Any = None
    supplier_prompt_resolution: Optional[SupplierPromptResolution] = None


def _hybrid_run_params_from_kwargs(kwargs: Mapping[str, Any]) -> _HybridRunParams:
    """Build params from ``process_video(..., **kwargs)``; ignores unknown keys (legacy ``**_``)."""
    missing = [k for k in _REQUIRED_HYBRID_KWARGS if k not in kwargs]
    if missing:
        raise TypeError(
            "process_video() missing required keyword argument(s): "
            + ", ".join(repr(k) for k in missing)
        )
    return _HybridRunParams(
        settings=kwargs["settings"],
        video_id=kwargs["video_id"],
        output_path=kwargs["output_path"],
        run_id=kwargs["run_id"],
        logger=kwargs["logger"],
        confidence_threshold=kwargs.get("confidence_threshold"),
        progress_callback=kwargs.get("progress_callback"),
        job_input=kwargs.get("job_input"),
        analysis_context=kwargs.get("analysis_context"),
        execution_observer=kwargs.get("execution_observer"),
        pipeline_provider_name=kwargs.get("pipeline_provider_name"),
        job_model_name=kwargs.get("job_model_name"),
        job_prompt_key=kwargs.get("job_prompt_key"),
        job_prompt_version=kwargs.get("job_prompt_version"),
        job_prompt_parity_mode=bool(kwargs.get("job_prompt_parity_mode", False)),
        cancellation_checkpoint=kwargs.get("cancellation_checkpoint"),
        supplier_prompt_resolution=kwargs.get("supplier_prompt_resolution"),
    )


@dataclass(frozen=True)
class _HybridMidPipelineState:
    """Snapshot after entity resolution (before evidence/reporting)."""

    prepared: PreparedInput
    acquired: AcquiredFrames
    analysis_result: AnalysisStageResult
    resolved: ResolvedEntities


def _ensure_job_input(video_path: str, job_input: Optional[JobInput]) -> JobInput:
    if job_input is None:
        return JobInput(video_path=video_path or "", mode="hybrid", input_type="video")
    return job_input


def _effective_analysis_context(
    job_input: JobInput, analysis_context: Optional[AnalysisContext]
) -> Optional[AnalysisContext]:
    """Prefer caller-supplied context; else parse from ``job_input.metadata['analysis_context']``."""
    if analysis_context is not None:
        return analysis_context
    raw_ctx = (getattr(job_input, "metadata", None) or {}).get("analysis_context")
    return analysis_context_from_dict(raw_ctx) if isinstance(raw_ctx, dict) else None


def _report_progress(
    progress_callback: Optional[Callable[[str, int], None]],
    logger: Any,
    job_id: str,
    stage: str,
    percent: int,
) -> None:
    if not callable(progress_callback):
        return
    try:
        progress_callback(stage, percent)
    except Exception:
        logger.warning(
            "progress_callback failed (ignored): stage=%s percent=%s job_id=%s",
            stage,
            percent,
            job_id,
            exc_info=True,
        )


def _fail_stage(
    exec_log: ExecutionLogWriter,
    context: RunContext,
    logger: Any,
    stage: str,
    exc: BaseException,
) -> PipelineRunResult:
    msg = str(exc).strip() or repr(exc)
    exec_log.error(stage, f"{stage} failed: {msg}", payload={"error": msg[:500]})
    context.emit_stage_event(
        stage=stage,
        event="stage.failed",
        details={"error": msg[:500]},
        level="error",
    )
    exec_log.write_last_stage_error(stage, msg)
    logger.exception("Stage failure: %s (job_id=%s): %s", stage, context.job_id, exc)
    return PipelineRunResult(exit_code=1, run_metadata=None)


def _fail_analysis_stage_llm(
    exec_log: ExecutionLogWriter,
    context: RunContext,
    logger: Any,
    exc: LLMProviderError,
) -> PipelineRunResult:
    exec_log.error(
        "AnalysisStage", f"LLM analysis failed: {exc}", payload={"error": str(exc)[:500]}
    )
    context.emit_stage_event(
        stage="AnalysisStage",
        event="stage.failed",
        details={"error": str(exc)[:500]},
        level="error",
    )
    exec_log.write_last_stage_error("AnalysisStage", str(exc))
    logger.exception("Stage failure: AnalysisStage (job_id=%s): %s", context.job_id, exc)
    return PipelineRunResult(exit_code=1, run_metadata=None)


def _build_success_run_metadata(
    context: RunContext,
    settings: Settings,
    analysis_result: AnalysisStageResult,
    logger: Any,
) -> dict[str, Any]:
    # Phase 5–6: run_metadata in memory; Phase 6 reuses analysis_result.prompt_composition
    # (same object as LLMRequest.metadata["prompt_composition"]) — no rebuild.
    run_metadata = build_run_metadata(
        context.analysis_context,
        analysis_result.provider_metadata,
        prompt_composition=analysis_result.prompt_composition,
        llm_cost_snapshot=getattr(analysis_result, "llm_cost_snapshot", None),
    )
    # Run attribution: provider + effective prompt profile key for job.result_json.
    # NOTE: top-level run_metadata["prompt_version"] below is legacy "{prompt_key}@v2.1" (report schema tag).
    # That is unrelated to prompt_composition["prompt_version"] (Phase 7 optional logical label).
    provider = (analysis_result.provider_name or "").strip() or None
    run_metadata["provider"] = provider
    prompt_key = getattr(context, "job_prompt_key", None) or getattr(
        settings, "hybrid_prompt", None
    )
    pc = analysis_result.prompt_composition
    pc = pc if isinstance(pc, dict) else None
    if pc:
        pn = pc.get("profile_name")
        if isinstance(pn, str) and pn.strip():
            prompt_key = pn.strip()
    if prompt_key is not None and str(prompt_key).strip():
        pk = str(prompt_key).strip()
        run_metadata["prompt_key"] = pk
        run_metadata["prompt_version"] = f"{pk}@v2.1"
    inv_id, aisle_id = context._execution_log_inventory_aisle_ids()
    spr = context.supplier_prompt_resolution
    resolved_model = (pc.get("model_name") if pc else None) or getattr(context, "job_model_name", None)
    resolved_model = str(resolved_model).strip() if resolved_model else None

    run_metadata[RUN_METADATA_KEY_RUN_AUDIT_SNAPSHOT] = build_run_audit_snapshot(
        run_metadata=run_metadata,
        inventory_id=inv_id,
        aisle_id=aisle_id,
        client_id=spr.client_id if spr else None,
        client_supplier_id=spr.client_supplier_id if spr else None,
        provider_name=provider,
        model_name=resolved_model or None,
        supplier_prompt_resolution=spr,
        analysis_context_available=context.analysis_context is not None,
        created_at_iso=datetime.now(timezone.utc).isoformat(),
    )

    if getattr(settings, "debug_run_metadata", False):
        try:
            (context.run_dir / "run_metadata.json").write_text(
                json.dumps(run_metadata, indent=2), encoding="utf-8"
            )
        except OSError as e:
            logger.warning("Failed to write run_metadata.json (job_id=%s): %s", context.job_id, e)
    return run_metadata


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
    indices = (
        frame_indices
        if frame_indices is not None and len(frame_indices) == len(frames)
        else list(range(len(frames)))
    )
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
        **kwargs: Any,
    ) -> PipelineRunResult:
        if mode != "hybrid":
            raise ValueError(f"Invalid mode: {mode!r}; only 'hybrid' is supported as of v2.2.")
        return self._run_hybrid(video_path, _hybrid_run_params_from_kwargs(kwargs))

    def _stage_input_preparation(
        self, context: RunContext, exec_log: ExecutionLogWriter
    ) -> PreparedInput:
        context.check_cancellation(
            stage="InputPreparationStage", reason="Job canceled before input preparation"
        )
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
        return prepared

    def _stage_frame_acquisition(
        self,
        context: RunContext,
        exec_log: ExecutionLogWriter,
        prepared: PreparedInput,
    ) -> AcquiredFrames:
        context.check_cancellation(
            stage="FrameAcquisitionStage", reason="Job canceled before frame acquisition"
        )
        stage_started = time.monotonic()
        exec_log.info("FrameAcquisitionStage", "Frame acquisition started")
        context.emit_stage_event(stage="FrameAcquisitionStage", event="stage.started")
        acquired: AcquiredFrames = self._frame_acquisition_stage.run(context, prepared)
        duration_ms = int((time.monotonic() - stage_started) * 1000)
        exec_log.info(
            "FrameAcquisitionStage",
            "Frame acquisition completed",
            payload={"frames": len(acquired.frames_nd)},
        )
        context.emit_stage_event(
            stage="FrameAcquisitionStage",
            event="stage.completed",
            details={"frames": len(acquired.frames_nd)},
            duration_ms=duration_ms,
        )
        return acquired

    def _stage_analysis(
        self,
        context: RunContext,
        exec_log: ExecutionLogWriter,
        acquired: AcquiredFrames,
    ) -> AnalysisStageResult:
        context.check_cancellation(stage="AnalysisStage", reason="Job canceled before analysis")
        stage_started = time.monotonic()
        exec_log.info("AnalysisStage", "LLM analysis started")
        context.emit_stage_event(stage="AnalysisStage", event="stage.started")
        analysis_result = self._analysis_stage.run(context, acquired)
        duration_ms = int((time.monotonic() - stage_started) * 1000)
        exec_log.info("AnalysisStage", "LLM analysis succeeded")
        context.emit_stage_event(
            stage="AnalysisStage", event="stage.completed", duration_ms=duration_ms
        )
        return analysis_result

    def _stage_entity_resolution(
        self,
        context: RunContext,
        exec_log: ExecutionLogWriter,
        analysis_result: AnalysisStageResult,
    ) -> ResolvedEntities:
        context.check_cancellation(
            stage="EntityResolutionStage", reason="Job canceled before entity resolution"
        )
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
        return resolved

    def _stage_evidence(
        self,
        context: RunContext,
        exec_log: ExecutionLogWriter,
        resolved: ResolvedEntities,
        acquired: AcquiredFrames,
    ) -> None:
        context.check_cancellation(
            stage="EvidenceStage", reason="Job canceled before evidence generation"
        )
        stage_started = time.monotonic()
        exec_log.info("EvidenceStage", "Evidence generation started")
        context.emit_stage_event(stage="EvidenceStage", event="stage.started")
        evidence_input = EvidenceStageInput(
            entities=resolved.entities,
            frames_nd=acquired.frames_nd,
            metadata=acquired.metadata,
            frame_refs=list(acquired.frame_refs),
        )
        self._evidence_stage.run(context, evidence_input)
        duration_ms = int((time.monotonic() - stage_started) * 1000)
        exec_log.info("EvidenceStage", "Evidence generation completed")
        context.emit_stage_event(
            stage="EvidenceStage", event="stage.completed", duration_ms=duration_ms
        )

    def _stage_reporting(
        self,
        context: RunContext,
        exec_log: ExecutionLogWriter,
        reporting_input: ReportingStageInput,
    ) -> None:
        context.check_cancellation(stage="ReportingStage", reason="Job canceled before reporting")
        stage_started = time.monotonic()
        exec_log.info("ReportingStage", "Reporting started")
        context.emit_stage_event(stage="ReportingStage", event="stage.started")
        self._reporting_stage.run(context, reporting_input)
        duration_ms = int((time.monotonic() - stage_started) * 1000)
        exec_log.info("ReportingStage", "Reporting completed")
        context.emit_stage_event(
            stage="ReportingStage", event="stage.completed", duration_ms=duration_ms
        )

    def _hybrid_begin(
        self, video_path: str, params: _HybridRunParams
    ) -> tuple[RunContext, ExecutionLogWriter]:
        execution_id = params.video_id
        job_input = _ensure_job_input(video_path, params.job_input)
        workspace_path = params.output_path
        run_dir = params.output_path / execution_id / params.run_id
        analysis_ctx = _effective_analysis_context(job_input, params.analysis_context)
        context = RunContext(
            job_id=execution_id,
            run_id=params.run_id,
            workspace_path=workspace_path,
            run_dir=run_dir,
            job_input=job_input,
            settings=params.settings,
            logger=params.logger,
            progress_callback=params.progress_callback,
            metadata={},
            analysis_context=analysis_ctx,
            execution_observer=params.execution_observer,
            cancellation_checkpoint=params.cancellation_checkpoint,
            pipeline_provider_name=params.pipeline_provider_name,
            job_model_name=params.job_model_name,
            job_prompt_key=params.job_prompt_key,
            job_prompt_version=params.job_prompt_version,
            job_prompt_parity_mode=params.job_prompt_parity_mode,
            supplier_prompt_resolution=params.supplier_prompt_resolution,
        )
        run_dir.mkdir(parents=True, exist_ok=True)
        exec_log = ExecutionLogWriter(run_dir)
        context.execution_log = exec_log

        exec_log.info("Pipeline", "Job started", payload={"job_id": execution_id})
        context.emit_stage_event(stage="Pipeline", event="job.started")
        return context, exec_log

    def _hybrid_run_through_entity_resolution(
        self,
        context: RunContext,
        exec_log: ExecutionLogWriter,
        params: _HybridRunParams,
    ) -> Union[PipelineRunResult, _HybridMidPipelineState]:
        logger = params.logger
        try:
            prepared = self._stage_input_preparation(context, exec_log)
        except PipelineCancellationRequestedError:
            raise
        except (FileNotFoundError, ValueError) as e:
            return _fail_stage(exec_log, context, logger, "InputPreparationStage", e)

        _report_progress(params.progress_callback, logger, context.job_id, "extract_frames", 10)
        try:
            acquired = self._stage_frame_acquisition(context, exec_log, prepared)
        except PipelineCancellationRequestedError:
            raise
        except (ValueError, FileNotFoundError, RuntimeError) as e:
            return _fail_stage(exec_log, context, logger, "FrameAcquisitionStage", e)

        _report_progress(
            params.progress_callback, logger, context.job_id, "global_analysis_call", 50
        )
        try:
            analysis_result = self._stage_analysis(context, exec_log, acquired)
        except PipelineCancellationRequestedError:
            raise
        except LLMProviderError as e:
            return _fail_analysis_stage_llm(exec_log, context, logger, e)

        try:
            resolved = self._stage_entity_resolution(context, exec_log, analysis_result)
        except PipelineCancellationRequestedError:
            raise
        except GlobalAnalysisParseError as e:
            return _fail_stage(exec_log, context, logger, "EntityResolutionStage", e)

        return _HybridMidPipelineState(
            prepared=prepared,
            acquired=acquired,
            analysis_result=analysis_result,
            resolved=resolved,
        )

    def _hybrid_evidence_reporting_finish(
        self,
        video_path: str,
        context: RunContext,
        exec_log: ExecutionLogWriter,
        params: _HybridRunParams,
        mid: _HybridMidPipelineState,
    ) -> PipelineRunResult:
        """Evidence → reporting → success metadata (same order and side effects as pre-B8.3)."""
        prepared = mid.prepared
        acquired = mid.acquired
        analysis_result = mid.analysis_result
        resolved = mid.resolved
        settings = params.settings
        logger = params.logger

        _report_progress(params.progress_callback, logger, context.job_id, "evidence_pack", 85)
        try:
            self._stage_evidence(context, exec_log, resolved, acquired)
        except PipelineCancellationRequestedError:
            raise
        except Exception as e:
            return _fail_stage(exec_log, context, logger, "EvidenceStage", e)

        video_path_for_report = video_path or (
            f"photos_{params.video_id}" if prepared.job_input.input_type == "photos" else ""
        )
        reporting_input = ReportingStageInput(
            entities=resolved.entities,
            frames_count=len(acquired.frames_nd),
            frame_indices=acquired.metadata.get("frame_indices"),
            video_path_for_report=video_path_for_report,
        )
        _report_progress(params.progress_callback, logger, context.job_id, "write_artifacts", 90)
        if getattr(settings, "debug_save_frames", False):
            _save_frames_sent_to_llm(
                context.run_dir, acquired.frames_nd, acquired.metadata.get("frame_indices")
            )
        try:
            self._stage_reporting(context, exec_log, reporting_input)
        except PipelineCancellationRequestedError:
            raise
        except Exception as e:
            return _fail_stage(exec_log, context, logger, "ReportingStage", e)

        run_metadata = _build_success_run_metadata(context, settings, analysis_result, logger)
        exec_log.info("Pipeline", "Job completed successfully")
        context.emit_stage_event(stage="Pipeline", event="job.succeeded")
        _report_progress(params.progress_callback, logger, context.job_id, "done", 100)
        return PipelineRunResult(exit_code=0, run_metadata=run_metadata)

    def _run_hybrid(self, video_path: str, params: _HybridRunParams) -> PipelineRunResult:
        """Orchestrate staged pipeline; return result with exit code and run_metadata (Phase 5).

        ``job_prompt_parity_mode``: when true, OpenAI hybrid **base** uses the same ``default`` branch
        as other providers (comparison). V3 jobs set this from ``engine_params_json.prompt_parity_mode``.
        """
        context, exec_log = self._hybrid_begin(video_path, params)
        mid_or_fail = self._hybrid_run_through_entity_resolution(context, exec_log, params)
        if isinstance(mid_or_fail, PipelineRunResult):
            return mid_or_fail
        return self._hybrid_evidence_reporting_finish(
            video_path, context, exec_log, params, mid_or_fail
        )
