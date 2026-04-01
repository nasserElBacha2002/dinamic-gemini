"""
Position domain entity — v3.0 (Documento técnico §7.4).

The revisable unit: a detected pallet/position. States: detected → reviewed | corrected | deleted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class PositionStatus(str, Enum):
    DETECTED = "detected"
    REVIEWED = "reviewed"
    CORRECTED = "corrected"
    DELETED = "deleted"


class PositionReviewResolution(str, Enum):
    """Final operator-facing review outcome.

    This is distinct from:
    - ``status``: operational lifecycle bucket for the position row
    - quantity provenance such as ``qty_source="unknown"``
    - pending review (represented by ``None`` while no terminal operator decision exists)
    """

    CONFIRMED = "confirmed"
    QTY_CORRECTED = "qty_corrected"
    SKU_CORRECTED = "sku_corrected"
    UNKNOWN = "unknown"
    DELETED = "deleted"


@dataclass
class Position:
    id: str
    aisle_id: str
    status: PositionStatus
    confidence: float
    needs_review: bool
    primary_evidence_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    review_resolution: Optional[PositionReviewResolution] = None
    detected_summary_json: Optional[Dict[str, Any]] = None
    corrected_summary_json: Optional[Dict[str, Any]] = None  # legacy persisted blob; Sprint 4 audit tracks removal readiness
