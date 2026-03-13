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
    detected_summary_json: Optional[Dict[str, Any]] = None
    corrected_summary_json: Optional[Dict[str, Any]] = None
