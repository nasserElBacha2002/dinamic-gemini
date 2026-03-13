"""
Stage 6 — Fallback trigger rules.

Determines whether a pallet should receive an additional visual counting pass.
"""

from typing import List, TypeVar

from src.domain.pallet import Pallet

DEFAULT_CONFIDENCE_THRESHOLD = 0.70

T = TypeVar("T")


def select_fallback_frames(frames: List[T], k: int = 3) -> List[T]:
    """Return a spread of up to k frames: first, mid, last. If len(frames) <= k, return all."""
    if not frames:
        return []
    if len(frames) <= k:
        return list(frames)
    mid = len(frames) // 2
    indices = [0, mid, len(frames) - 1][:k]
    return [frames[i] for i in indices]


def should_trigger_fallback(pallet: Pallet, confidence_threshold: float) -> bool:
    """Return True if a pallet should trigger a visual fallback counting pass.

    Trigger fallback if any of:
    - pallet.source == "visual_fallback"
    - pallet.confidence < confidence_threshold
    - pallet.has_label is True AND pallet.quantity is None

    Args:
        pallet: Pallet after assign_processing_mode.
        confidence_threshold: Minimum confidence to skip fallback.

    Returns:
        True if fallback should run for this pallet.
    """
    if pallet.source == "visual_fallback":
        return True
    if pallet.confidence < confidence_threshold:
        return True
    if pallet.has_label and pallet.quantity is None:
        return True
    return False
