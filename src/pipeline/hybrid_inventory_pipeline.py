"""
Hybrid inventory pipeline (v2.1).
Stage 2.2.B: frames obtained via FrameSource (video or photos); pipeline input-agnostic.
"""

from pathlib import Path
from typing import Any, Callable, List, Optional

import cv2
import numpy as np

from src.config import Settings
from src.decision.count_status import assign_count_status
from src.decision.entity_order import sort_entities_deterministically
from src.decision.pallet_id import resolve_pallet_id
from src.decision.quality_score import compute_entity_quality_score
from src.exceptions.global_analysis_exceptions import (
    GlobalAnalysisParsingError,
    GlobalAnalysisValidationError,
)
from src.frames.sources.factory import get_frame_source
from src.jobs.models import JobInput
from src.llm.gemini_client import GeminiClient
from src.llm.gemini_global_analyzer import GeminiGlobalAnalyzer
from src.llm.global_pallet_analysis_prompt import GLOBAL_ENTITY_ANALYSIS_PROMPT_V21
from src.parsing.global_analysis_parser import GlobalAnalysisParseError, parse_entities
from src.pipeline.legacy_visual_pipeline import LegacyVisualPipeline
from src.evidence.evidence_pack import generate_evidence_pack
from src.reporting.artifacts import write_json
from src.reporting.hybrid_report import build_hybrid_report
from src.validation.global_analysis_schema import validate_global_analysis_structure_v21

# Default max frames when hybrid_max_frames is None (kept for test imports)
# Hard cap for loading into RAM when env is unset (avoid unbounded memory)
HYBRID_MAX_FRAMES = 10000
HYBRID_MAX_FRAMES_LOAD_CAP = 48


def _save_frames_sent_to_gemini(
    run_dir: Path,
    frames: List[np.ndarray],
    frame_indices: Optional[List[int]] = None,
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
    """Controller: runs legacy or hybrid path based on mode."""

    def __init__(self) -> None:
        self.legacy_pipeline = LegacyVisualPipeline()

    def process_video(
        self,
        video_path: str,
        mode: str = "legacy",
        **kwargs: object,
    ) -> int:
        if mode == "legacy":
            return self.legacy_pipeline.run(video_path, **kwargs)
        if mode == "hybrid":
            return self._run_hybrid(video_path, **kwargs)
        raise ValueError(f"Invalid mode: {mode!r}")

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
        """Hybrid flow: get frames via FrameSource → one Gemini call → parse → entities (v2.1)."""
        progress_cb = progress_callback
        def _report(stage: str, percent: int) -> None:
            if callable(progress_cb):
                try:
                    progress_cb(stage, percent)
                except Exception:
                    pass
        _report("extract_frames", 10)
        if job_input is None:
            job_input = JobInput(video_path=video_path or "", mode="hybrid", input_type="video")
        run_dir = output_path / video_id / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        try:
            frame_source = get_frame_source(job_input.input_type)
            bundle = frame_source.get_frames(video_id, run_dir, job_input)
        except (ValueError, FileNotFoundError, RuntimeError) as e:
            logger.exception("Error obtaining frames (FrameSource): %s", e)
            return 1
        # Hard cap on frames loaded into RAM (settings.hybrid_max_frames or safe default)
        max_load = getattr(settings, "hybrid_max_frames", None)
        if max_load is None or not isinstance(max_load, (int, float)) or max_load <= 0:
            max_load = HYBRID_MAX_FRAMES_LOAD_CAP
        frames_to_load = bundle.frames[: int(max_load)]
        frames_nd: List[np.ndarray] = []
        for p in frames_to_load:
            img = cv2.imread(str(p))
            if img is not None:
                frames_nd.append(img)
        if not frames_nd:
            logger.warning("No frames could be loaded from bundle (frame_count=%s)", bundle.metadata.get("frame_count"))
            return 1
        metadata = {**bundle.metadata, "frame_count": len(frames_nd)}
        logger.info("Frames loaded: %d (source=%s)", len(frames_nd), metadata.get("source", "unknown"))

        if not settings.gemini_api_key:
            logger.error("GEMINI_API_KEY no configurada")
            return 1
        client = GeminiClient(
            api_key=settings.gemini_api_key,
            model_name=settings.gemini_model_name,
            max_retries=settings.gemini_max_retries,
            retry_delay=settings.gemini_retry_delay,
        )
        _report("gemini_global_call", 50)
        run_dir = output_path / video_id / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        analyzer = GeminiGlobalAnalyzer(client)
        try:
            data = analyzer.analyze_video_frames(frames_nd, logger=logger)
        except (RuntimeError, ValueError) as e:
            logger.exception("Error en análisis global Gemini: %s", e)
            return 1
        except GlobalAnalysisParsingError as e:
            logger.exception("Respuesta de Gemini no es JSON válido (parsing): %s", e)
            return 1
        except GlobalAnalysisValidationError as e:
            logger.exception("Respuesta de Gemini no cumple schema v2.1: %s", e)
            return 1
        try:
            entities = parse_entities(data, job_id=video_id)
        except GlobalAnalysisParseError as e:
            logger.exception("Error parseando entidades: %s", e)
            return 1
        logger.info("Entidades detectadas (hybrid v2.1): %d", len(entities))

        sort_entities_deterministically(entities)
        resolve_pallet_id(entities)
        for e in entities:
            assign_count_status(e)
        for e in entities:
            compute_entity_quality_score(e)

        _report("evidence_pack", 85)
        generate_evidence_pack(
            job_id=video_id,
            run_dir=run_dir,
            frames=frames_nd,
            metadata=metadata,
            entities=entities,
        )
        report_video_path = video_path or (f"photos_{video_id}" if job_input.input_type == "photos" else "")
        report = build_hybrid_report(
            video_path=report_video_path,
            entities=entities,
            frames_selected=len(frames_nd),
            frame_indices=metadata.get("frame_indices"),
        )
        _report("write_artifacts", 90)
        if getattr(settings, "debug_save_frames", False):
            _save_frames_sent_to_gemini(run_dir, frames_nd, metadata.get("frame_indices"))
        report_path = run_dir / "hybrid_report.json"
        write_json(report_path, report)
        logger.info("Reporte hybrid v2.1 guardado: %s", report_path)
        _report("done", 100)
        return 0
