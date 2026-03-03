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
