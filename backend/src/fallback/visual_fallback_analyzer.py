"""
Stage 6 — Visual fallback analyzer: small Gemini call to count visible boxes.

Uses 3–5 frames, minimal JSON prompt, strict validation.
"""

import json
import re
from typing import List, Tuple

import numpy as np

from src.llm.gemini_client import GeminiClient

FALLBACK_MAX_FRAMES = 5

FALLBACK_COUNT_PROMPT = """\
You see a few frames that may show one or more pallets. Count the number of visible boxes on the main pallet (the most central or dominant pallet in view). Ignore other pallets in the background.

Return ONLY valid JSON, no other text:
{"estimated_count": <integer>, "confidence": <float in [0, 1]>}
"""


class VisualFallbackError(Exception):
    """Raised when fallback count request or response fails."""

    pass


def _frame_to_pil(frame: np.ndarray):
    """BGR (OpenCV) to PIL RGB."""
    import cv2
    try:
        from PIL import Image
    except ImportError:
        raise ImportError("Pillow required for fallback analyzer. Install with: pip install pillow")
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def _strip_json(text: str) -> str:
    """Extract JSON: fenced block first, else first { to last }."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        return match.group(1).strip()
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1 and last >= first:
        return text[first : last + 1]
    return text


def _validate_fallback_response(data: dict) -> Tuple[int, float]:
    """Validate and return (estimated_count, confidence). Raises VisualFallbackError on failure."""
    if not isinstance(data, dict):
        raise VisualFallbackError("Fallback response must be a JSON object")
    if "estimated_count" not in data:
        raise VisualFallbackError("Fallback response missing 'estimated_count'")
    if "confidence" not in data:
        raise VisualFallbackError("Fallback response missing 'confidence'")
    try:
        count = int(data["estimated_count"])
    except (TypeError, ValueError):
        raise VisualFallbackError(f"estimated_count must be integer, got {type(data['estimated_count']).__name__!r}")
    try:
        conf = float(data["confidence"])
    except (TypeError, ValueError):
        raise VisualFallbackError(f"confidence must be number, got {type(data['confidence']).__name__!r}")
    if not (0 <= conf <= 1):
        raise VisualFallbackError(f"confidence must be in [0, 1], got {conf}")
    if count < 0:
        raise VisualFallbackError(f"estimated_count must be non-negative, got {count}")
    return count, conf


class VisualFallbackAnalyzer:
    """Per-pallet visual counting via a small Gemini call (3–5 frames)."""

    def __init__(self, client: GeminiClient) -> None:
        self.client = client

    def count_visible_boxes(self, frames: List[np.ndarray]) -> Tuple[int, float]:
        """Perform a small Gemini call to count visible boxes on the pallet.

        Uses at most FALLBACK_MAX_FRAMES frames. Returns (estimated_count, confidence).

        Args:
            frames: List of BGR frames (OpenCV). Will use frames[:FALLBACK_MAX_FRAMES].

        Returns:
            (estimated_count, confidence).

        Raises:
            VisualFallbackError: If frames empty, or response invalid.
            RuntimeError: If Gemini call fails after retries.
        """
        if not frames:
            raise VisualFallbackError("frames cannot be empty")
        subset = frames[:FALLBACK_MAX_FRAMES]
        images = [_frame_to_pil(f) for f in subset]
        raw = self.client.generate_global_analysis_raw(images, FALLBACK_COUNT_PROMPT)
        cleaned = _strip_json(raw)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise VisualFallbackError(f"Fallback response invalid JSON: {e}") from e
        return _validate_fallback_response(data)
