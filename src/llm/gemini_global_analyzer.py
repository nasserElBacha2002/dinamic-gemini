"""
Análisis global de video con una sola llamada a Gemini (v2.0 hybrid).

Stage 3: robust JSON extraction, structural validation, typed exceptions.
"""

import json
import logging
import re
from typing import Any, Dict, List

import numpy as np

from src.exceptions.global_analysis_exceptions import (
    GlobalAnalysisParsingError,
    GlobalAnalysisValidationError,
)
from src.llm.global_pallet_analysis_prompt import GLOBAL_PALLET_ANALYSIS_PROMPT
from src.llm.gemini_client import GeminiClient
from src.validation.global_analysis_schema import validate_global_analysis_structure

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


def _strip_json_wrapper(text: str) -> str:
    """Extrae JSON del texto: primero bloques ```json ... ```; si no, primer { hasta último }."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        return match.group(1).strip()
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1 and last >= first:
        return text[first : last + 1]
    return text


class GeminiGlobalAnalyzer:
    """Una llamada a Gemini con todos los frames; devuelve dict JSON."""

    def __init__(self, client: GeminiClient) -> None:
        self.client = client

    def analyze_video_frames(
        self, frames: List[np.ndarray], **kwargs: object
    ) -> Dict[str, Any]:
        """Envía los frames en una sola llamada a Gemini y devuelve el JSON validado.

        Flow: raw response → JSON extraction → json.loads → structure validation → return.
        Retries are not performed in this class; RuntimeError may propagate from GeminiClient.

        Args:
            frames: Lista de frames BGR (OpenCV).
            **kwargs: Optional run logger (e.g. logger=logger). If provided, used for all log output.

        Returns:
            Dict con "total_pallets_detected" y "pallets" (lista de dicts).

        Raises:
            ValueError: Si frames está vacía.
            RuntimeError: Si el cliente Gemini falla (puede incluir reintentos en el cliente).
            GlobalAnalysisParsingError: Si la respuesta no es JSON válido.
            GlobalAnalysisValidationError: Si la estructura no cumple el schema.
        """
        if not frames:
            raise ValueError("frames no puede estar vacía")
        run_logger = kwargs.get("logger")
        log = run_logger if run_logger is not None else logger
        images = [_ndarray_to_pil(f) for f in frames]
        log.info("Enviando %d frames a Gemini (análisis global único)...", len(frames))
        raw = self.client.generate_global_analysis_raw(images, GLOBAL_PALLET_ANALYSIS_PROMPT)
        cleaned = _strip_json_wrapper(raw)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            log.warning("Global analysis parsing failed (invalid JSON): %s", e)
            raise GlobalAnalysisParsingError(f"Invalid JSON: {e}") from e
        try:
            validate_global_analysis_structure(data)
        except GlobalAnalysisValidationError as e:
            log.warning("Global analysis validation failed: %s", e)
            raise
        return data
