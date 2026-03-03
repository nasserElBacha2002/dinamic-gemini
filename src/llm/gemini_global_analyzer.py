"""
Análisis global de video con una sola llamada a Gemini (v2.0 hybrid).

Envía todos los frames representativos en una request y devuelve el JSON parseado.
"""

import json
import logging
import re
from typing import Any, Dict, List

import numpy as np

from src.llm.global_pallet_analysis_prompt import GLOBAL_PALLET_ANALYSIS_PROMPT
from src.llm.gemini_client import GeminiClient

logger = logging.getLogger(__name__)


def _ndarray_to_pil(frame: np.ndarray):
    """Convierte frame BGR (OpenCV) a PIL Image RGB."""
    import cv2
    try:
        from PIL import Image
    except ImportError:
        raise ImportError("Pillow required for global analyzer")
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

    def analyze_video_frames(self, frames: List[np.ndarray]) -> Dict[str, Any]:
        """Envía los frames en una sola llamada a Gemini y devuelve el JSON parseado.

        Args:
            frames: Lista de frames BGR (OpenCV).

        Returns:
            Dict con "total_pallets_detected" y "pallets" (lista de dicts).

        Raises:
            ValueError: Si frames está vacía.
            RuntimeError: Si Gemini falla tras reintentos.
            json.JSONDecodeError: Si la respuesta no es JSON válido (caller puede capturar).
        """
        if not frames:
            raise ValueError("frames no puede estar vacía")
        images = [_ndarray_to_pil(f) for f in frames]
        logger.info("Enviando %d frames a Gemini (análisis global único)...", len(frames))
        raw = self.client.generate_global_analysis_raw(images, GLOBAL_PALLET_ANALYSIS_PROMPT)
        cleaned = _strip_json_wrapper(raw)
        return json.loads(cleaned)
