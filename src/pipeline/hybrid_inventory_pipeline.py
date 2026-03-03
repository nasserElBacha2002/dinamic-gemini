"""
Hybrid inventory pipeline (v2.0 controller).

Dispatches to legacy or hybrid path based on --mode.
Hybrid: una llamada global a Gemini, frames representativos, lista de Pallet.
"""

import json
from pathlib import Path
from typing import Any, Callable, List, Optional

import numpy as np

from src.config import Settings
from src.decision.processing_mode import assign_processing_mode
from src.exceptions.global_analysis_exceptions import (
    GlobalAnalysisParsingError,
    GlobalAnalysisValidationError,
)
from src.fallback.fallback_policy import DEFAULT_CONFIDENCE_THRESHOLD, should_trigger_fallback
from src.fallback.visual_fallback_analyzer import VisualFallbackAnalyzer, VisualFallbackError
from src.llm.gemini_client import GeminiClient
from src.llm.gemini_global_analyzer import GeminiGlobalAnalyzer
from src.parsing.global_analysis_parser import GlobalAnalysisParseError, parse_global_analysis
from src.pipeline.legacy_visual_pipeline import LegacyVisualPipeline
from src.reporting.artifacts import write_csv, write_json
from src.reporting.hybrid_report import build_hybrid_report
from src.video.frames import STRATEGY_OPTIMIZED, extract_representative_frames

FALLBACK_FRAMES_SUBSET = 3

HYBRID_MAX_FRAMES = 25


def select_fallback_frames(frames: List[np.ndarray], k: int) -> List[np.ndarray]:
    """Select up to k frames spread across the list (first, mid, last for k=3). Deterministic."""
    if not frames or k <= 0:
        return []
    n = len(frames)
    if n <= k:
        return list(frames)
    if k == 1:
        return [frames[0]]
    # k=3: first, mid, last; else evenly spread
    if k == 3:
        indices = [0, n // 2, n - 1]
    else:
        indices = [int(i * (n - 1) / (k - 1)) for i in range(k)]
        indices = [min(max(i, 0), n - 1) for i in indices]
    return [frames[i] for i in indices]


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
        **_: object,
    ) -> int:
        """Flujo hybrid: extraer frames → una llamada Gemini → parsear → lista de Pallet."""
        progress_cb = progress_callback
        def _report(stage: str, percent: int) -> None:
            if callable(progress_cb):
                try:
                    progress_cb(stage, percent)
                except Exception:
                    pass
        _report("extract_frames", 10)
        logger.info("Hybrid mode: análisis global (una llamada por video)")
        try:
            frames, metadata = extract_representative_frames(
                video_path,
                max_frames=HYBRID_MAX_FRAMES,
                strategy=STRATEGY_OPTIMIZED,
            )
        except (RuntimeError, ValueError) as e:
            logger.exception("Error extrayendo frames representativos: %s", e)
            return 1
        if not frames:
            logger.warning("No se extrajeron frames del video")
            return 1
        logger.info("Frames representativos: %d (fps=%s)", len(frames), metadata.get("fps"))

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
        analyzer = GeminiGlobalAnalyzer(client)
        try:
            data = analyzer.analyze_video_frames(frames, logger=logger)
        except (RuntimeError, ValueError) as e:
            logger.exception("Error en análisis global Gemini: %s", e)
            return 1
        except GlobalAnalysisParsingError as e:
            logger.exception("Respuesta de Gemini no es JSON válido (parsing): %s", e)
            return 1
        except GlobalAnalysisValidationError as e:
            logger.exception("Respuesta de Gemini no cumple schema (validación): %s", e)
            return 1
        try:
            pallets = parse_global_analysis(data)
        except GlobalAnalysisParseError as e:
            logger.exception("Error validando respuesta global: %s", e)
            return 1
        logger.info("Pallets detectados (hybrid): %d", len(pallets))

        threshold = confidence_threshold if confidence_threshold is not None else DEFAULT_CONFIDENCE_THRESHOLD
        pallets_with_mode = [assign_processing_mode(p) for p in pallets]
        fallback_analyzer = VisualFallbackAnalyzer(client)
        fallback_attempts = 0
        fallback_success = 0
        for pallet in pallets_with_mode:
            if should_trigger_fallback(pallet, threshold):
                fallback_frames = select_fallback_frames(frames, FALLBACK_FRAMES_SUBSET)
                fallback_attempts += 1
                try:
                    count, conf = fallback_analyzer.count_visible_boxes(fallback_frames)
                    pallet.final_quantity = count
                    pallet.fallback_used = True
                    pallet.confidence = conf
                    fallback_success += 1
                except (VisualFallbackError, RuntimeError) as e:
                    logger.warning("Fallback para pallet %s falló: %s", pallet.pallet_id, e)

        _report("fallback_calls", 70)
        global_calls = 1
        total_calls = global_calls + fallback_attempts
        metrics = {
            "global_calls": global_calls,
            "fallback_attempts": fallback_attempts,
            "fallback_success": fallback_success,
            "total_calls": total_calls,
        }
        report = build_hybrid_report(
            video_path=video_path,
            pallets=pallets_with_mode,
            frames_selected=len(frames),
            prompt_version="global_min_v1",
            metrics=metrics,
            confidence_threshold=threshold,
        )

        _report("write_artifacts", 90)
        run_dir = output_path / video_id / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        report_path = run_dir / "hybrid_report.json"
        write_json(report_path, report)
        logger.info("Reporte hybrid guardado: %s", report_path)
        write_csv(run_dir / "hybrid_report.csv", pallets_with_mode)

        # Debug artifact only — NOT the public contract. Use hybrid_report.json for integration.
        debug_path = run_dir / "hybrid_debug.json"
        with open(debug_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "video_id": video_id,
                    "mode": "hybrid",
                    "total_pallets_detected": len(pallets),
                    "pallets": [
                        {
                            "pallet_id": p.pallet_id,
                            "has_label": p.has_label,
                            "internal_code": p.internal_code,
                            "quantity": p.quantity,
                            "final_quantity": p.final_quantity,
                            "source": p.source,
                            "estimated_visible_boxes": p.estimated_visible_boxes,
                            "confidence": p.confidence,
                            "fallback_used": p.fallback_used,
                        }
                        for p in pallets_with_mode
                    ],
                    "metadata": metadata,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )
        logger.info("Debug hybrid guardado: %s", debug_path)
        _report("done", 100)
        return 0
