"""
Position domain entity — v3.0 (Documento técnico §7.4).

The revisable unit: a detected pallet/position. States: detected → reviewed | corrected | deleted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


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
    - product-identification issues such as a display-primary product row with ``sku="UNKNOWN"``
    - pending review (represented by ``None`` while no terminal operator decision exists)

    ``IMAGE_MISMATCH``: operator says evidence/image linkage is wrong; does not imply SKU/qty or
    product identification errors (traceability-only flag).
    """

    CONFIRMED = "confirmed"
    QTY_CORRECTED = "qty_corrected"
    SKU_CORRECTED = "sku_corrected"
    POSITION_CODE_CORRECTED = "position_code_corrected"
    UNKNOWN = "unknown"
    IMAGE_MISMATCH = "image_mismatch"
    DELETED = "deleted"


@dataclass
class Position:
    id: str
    aisle_id: str
    status: PositionStatus
    confidence: float
    needs_review: bool
    primary_evidence_id: str | None
    created_at: datetime
    updated_at: datetime
    review_resolution: PositionReviewResolution | None = None
    detected_summary_json: dict[str, Any] | None = None
    corrected_summary_json: dict[str, Any] | None = (
        None  # legacy persisted blob; Sprint 4 audit tracks removal readiness
    )
    corrected_position_code: str | None = None
    #: FK to ``inventory_jobs`` when persisted from a pipeline run; ``None`` = legacy pre-multi-run row.
    job_id: str | None = None
