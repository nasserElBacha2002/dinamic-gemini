"""
Análisis global de video con una sola llamada a Gemini (hybrid v2.1, Structured Output).
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

import numpy as np

from src.exceptions.global_analysis_exceptions import (
    GlobalAnalysisParsingError,
    GlobalAnalysisValidationError,
)
from src.llm.gemini_client import GeminiClient
from src.llm.prompt_composer.hybrid_assembly import compose_hybrid_base
from src.llm.types import ContextImageSequence
from src.models.schemas import GlobalEntityResponseV21
from src.validation.global_analysis_schema import validate_global_analysis_structure_v21

logger = logging.getLogger(__name__)


def _ndarray_to_pil(frame: np.ndarray):
    """Convierte frame BGR (OpenCV) a PIL Image RGB."""
    import cv2
    try:
        from PIL import Image
    except ImportError:
        raise ImportError("Pillow required for global analyzer. Install with: pip install pillow")
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


class GeminiGlobalAnalyzer:
    """Una llamada a Gemini con todos los frames; devuelve dict JSON."""

    def __init__(self, client: GeminiClient, prompt_text: str | None = None) -> None:
        self.client = client
        self._prompt_text = prompt_text

    def analyze_video_frames(
        self,
        frames: List[np.ndarray],
        *,
        context_instruction: Optional[str] = None,
        context_images: Optional[ContextImageSequence] = None,
        **kwargs: object,
    ) -> Dict[str, Any]:
        """Envía los frames en una sola llamada a Gemini (Structured Output v2.1) y devuelve el JSON validado.

        Usa response_schema para que Gemini devuelva JSON conforme a GlobalEntityResponseV21.
        v3.2.4 Phase 4: optional context_instruction + context_images (e.g. visual references) prepended to the call.

        Args:
            frames: Lista de frames BGR (OpenCV).
            context_instruction: Optional text instruction (e.g. visual reference description) sent before context images.
            context_images: Optional list of PIL images (context/reference) sent before primary frames.
            **kwargs: Optional run logger (e.g. logger=logger), save_raw_to_path.

        Returns:
            Dict con total_entities_detected y entities.
        """
        if not frames:
            raise ValueError("frames no puede estar vacía")
        run_logger = kwargs.get("logger")
        log: logging.Logger = (
            run_logger if isinstance(run_logger, logging.Logger) else logger
        )
        primary_images = [_ndarray_to_pil(f) for f in frames]
        prompt = (
            self._prompt_text
            if self._prompt_text is not None
            else compose_hybrid_base("global_v21", None)
        )
        # v3.2.4: apply context_instruction and context_images independently
        if context_instruction and context_instruction.strip():
            prompt = context_instruction.strip() + "\n\n" + prompt
        if context_images:
            images = list(context_images) + primary_images
            log.info(
                "Enviando %d context + %d frames a Gemini (análisis global v2.1 structured)...",
                len(context_images),
                len(frames),
            )
        else:
            images = primary_images
            log.info("Enviando %d frames a Gemini (análisis global v2.1 structured)...", len(frames))
        raw = self.client.generate_global_analysis_structured(images, prompt, GlobalEntityResponseV21)
        cleaned = raw.strip()
        save_raw_to_path = kwargs.get("save_raw_to_path")
        if save_raw_to_path is not None:
            p = Path(str(save_raw_to_path))
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(cleaned, encoding="utf-8")
            log.info("Respuesta cruda de Gemini guardada en %s", p)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as e:
            log.warning("Global analysis parsing failed (invalid JSON): %s", e)
            raise GlobalAnalysisParsingError(f"Invalid JSON: {e}") from e
        if not isinstance(parsed, dict):
            raise GlobalAnalysisParsingError("Global analysis response must be a JSON object")

        data = parsed

        # Normalize Gemini count mismatch: trust len(entities) as source of truth (deterministic, auditable)
        total = data.get("total_entities_detected")
        entities = data.get("entities") or []
        if isinstance(entities, list) and isinstance(total, (int, float)) and total != len(entities):
            log.warning(
                "Gemini count mismatch: total_entities_detected=%s vs len(entities)=%d; normalizing to len(entities)",
                total,
                len(entities),
            )
            data["total_entities_detected"] = len(entities)

        try:
            validate_global_analysis_structure_v21(data)
        except GlobalAnalysisValidationError as e:
            log.warning("Global analysis validation failed: %s", e)
            raise
        return cast(Dict[str, Any], data)
