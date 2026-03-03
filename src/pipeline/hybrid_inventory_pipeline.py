"""
Hybrid inventory pipeline (v2.0 controller).

Dispatches to legacy or hybrid path based on --mode.
Hybrid: una llamada global a Gemini, frames representativos, lista de Pallet.
"""

import json
from pathlib import Path
from typing import Any, List

from src.config import Settings
from src.domain.pallet import Pallet
from src.llm.gemini_client import GeminiClient
from src.llm.gemini_global_analyzer import GeminiGlobalAnalyzer
from src.parsing.global_analysis_parser import GlobalAnalysisParseError, parse_global_analysis
from src.pipeline.legacy_visual_pipeline import LegacyVisualPipeline
from src.video.frames import extract_representative_frames

HYBRID_MAX_FRAMES = 25


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
        **_: object,
    ) -> int:
        """Flujo hybrid: extraer frames → una llamada Gemini → parsear → lista de Pallet."""
        logger.info("Hybrid mode: análisis global (una llamada por video)")
        try:
            frames, metadata = extract_representative_frames(
                video_path,
                max_frames=HYBRID_MAX_FRAMES,
                strategy="uniform",
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
        analyzer = GeminiGlobalAnalyzer(client)
        try:
            data = analyzer.analyze_video_frames(frames)
        except (RuntimeError, ValueError) as e:
            logger.exception("Error en análisis global Gemini: %s", e)
            return 1
        except json.JSONDecodeError as e:
            logger.exception("Respuesta de Gemini no es JSON válido: %s", e)
            return 1
        try:
            pallets = parse_global_analysis(data)
        except GlobalAnalysisParseError as e:
            logger.exception("Error validando respuesta global: %s", e)
            return 1
        logger.info("Pallets detectados (hybrid): %d", len(pallets))

        run_dir = output_path / video_id / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        report = {
            "video_id": video_id,
            "mode": "hybrid",
            "total_pallets_detected": len(pallets),
            "pallets": [
                {
                    "pallet_id": p.pallet_id,
                    "has_label": p.has_label,
                    "internal_code": p.internal_code,
                    "quantity": p.quantity,
                    "estimated_visible_boxes": p.estimated_visible_boxes,
                    "confidence": p.confidence,
                }
                for p in pallets
            ],
            "metadata": metadata,
        }
        result_file = run_dir / "hybrid_result.json"
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        logger.info("Resultado hybrid guardado: %s", result_file)
        return 0
