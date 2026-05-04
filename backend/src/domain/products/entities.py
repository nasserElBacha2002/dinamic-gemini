"""
ProductRecord domain entity — v3.0 (Documento técnico §7.5).

Product detected within a position; corrected_quantity set by review.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


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
    description: str | None = None
    corrected_quantity: int | None = None
    # Quantity provenance (auditable, persisted). Keep as string for DB compatibility.
    # Expected values evolve by phase: detected, inferred, merge_inferred, manual_review,
    # label_explicit, ocr, llm_extracted, fallback, unknown (legacy: consolidated).
    qty_source: str | None = None
    qty_inference_reason: str | None = None
    raw_qty: object | None = None
    qty_parse_status: str | None = None  # missing | null | invalid | zero | valid_positive
