"""
Stage 6 — Fallback trigger rules.

Determines whether a pallet should receive an additional visual counting pass.
"""

from src.domain.pallet import Pallet

DEFAULT_CONFIDENCE_THRESHOLD = 0.70


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
