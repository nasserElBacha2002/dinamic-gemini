"""Modelo de pallet para análisis global (v2.0)."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Pallet:
    """Pallet detectado en análisis global (una llamada por video)."""

    pallet_id: str
    has_label: bool
    internal_code: Optional[str]
    quantity: Optional[int]
    estimated_visible_boxes: Optional[int]
    confidence: float
    processing_mode: Optional[str] = None
    # Stage 4: operational output
    final_quantity: Optional[int] = None
    fallback_used: bool = False
    source: str = (
        "unknown"  # "label" | "visual_fallback" after assign_processing_mode; "unknown" if skipped
    )
