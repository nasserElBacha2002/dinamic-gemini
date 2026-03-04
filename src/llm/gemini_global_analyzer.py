"""
Análisis global de video con una sola llamada a Gemini (hybrid v2.1, Structured Output).
"""

import json
import logging
from typing import Any, Dict, List

import numpy as np

from src.exceptions.global_analysis_exceptions import (
    GlobalAnalysisParsingError,
    GlobalAnalysisValidationError,
)
from src.llm.global_pallet_analysis_prompt import GLOBAL_ENTITY_ANALYSIS_PROMPT_V21
from src.llm.gemini_client import GeminiClient
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

    def __init__(self, client: GeminiClient) -> None:
        self.client = client

    def analyze_video_frames(
        self,
        frames: List[np.ndarray],
        **kwargs: object,
    ) -> Dict[str, Any]:
        """Envía los frames en una sola llamada a Gemini (Structured Output v2.1) y devuelve el JSON validado.

        Usa response_schema para que Gemini devuelva JSON conforme a GlobalEntityResponseV21.

        Args:
            frames: Lista de frames BGR (OpenCV).
            **kwargs: Optional run logger (e.g. logger=logger).

        Returns:
            Dict con total_entities_detected y entities.
        """
        if not frames:
            raise ValueError("frames no puede estar vacía")
        run_logger = kwargs.get("logger")
        log = run_logger if run_logger is not None else logger
        images = [_ndarray_to_pil(f) for f in frames]
        log.info("Enviando %d frames a Gemini (análisis global v2.1 structured)...", len(frames))
        raw = self.client.generate_global_analysis_structured(images, GLOBAL_ENTITY_ANALYSIS_PROMPT_V21, GlobalEntityResponseV21)
        cleaned = raw.strip()
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            log.warning("Global analysis parsing failed (invalid JSON): %s", e)
            raise GlobalAnalysisParsingError(f"Invalid JSON: {e}") from e
        try:
            validate_global_analysis_structure_v21(data)
        except GlobalAnalysisValidationError as e:
            log.warning("Global analysis validation failed: %s", e)
            raise
        return data
