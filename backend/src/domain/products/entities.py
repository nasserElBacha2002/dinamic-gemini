"""
ProductRecord domain entity — v3.0 (Documento técnico §7.5).

Product detected within a position; corrected_quantity set by review.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ProductRecord:
    id: str
    position_id: str
    sku: str
    description: str
    detected_quantity: int
    confidence: float
    created_at: datetime
    updated_at: datetime
    corrected_quantity: Optional[int] = None
    # v3.2.2 — quantity provenance (auditable, persisted)
    qty_source: Optional[str] = None  # detected | inferred | consolidated (string for DB compatibility)
    qty_inference_reason: Optional[str] = None
    raw_qty: Optional[object] = None
    qty_parse_status: Optional[str] = None  # missing | null | invalid | zero | valid_positive
