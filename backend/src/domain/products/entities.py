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
    detected_quantity: int
    confidence: float
    created_at: datetime
    updated_at: datetime
    #: Nullable in storage and after review clears whitespace-only input to ``None``.
    description: Optional[str] = None
    corrected_quantity: Optional[int] = None
    # Quantity provenance (auditable, persisted). Keep as string for DB compatibility.
    # Expected values evolve by phase: detected, inferred, merge_inferred, manual_review,
    # label_explicit, ocr, llm_extracted, fallback, unknown (legacy: consolidated).
    qty_source: Optional[str] = None
    qty_inference_reason: Optional[str] = None
    raw_qty: Optional[object] = None
    qty_parse_status: Optional[str] = None  # missing | null | invalid | zero | valid_positive
