"""Stage 6 — Confidence-gated visual fallback (pallet-level)."""

from src.fallback.fallback_policy import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    select_fallback_frames,
    should_trigger_fallback,
)
from src.fallback.visual_fallback_analyzer import VisualFallbackAnalyzer, VisualFallbackError

__all__ = [
    "DEFAULT_CONFIDENCE_THRESHOLD",
    "VisualFallbackAnalyzer",
    "VisualFallbackError",
    "select_fallback_frames",
    "should_trigger_fallback",
]
