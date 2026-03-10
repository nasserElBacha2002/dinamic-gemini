"""
Evidence domain entity — v3.0 (Documento técnico §7.6).

Visual evidence linked to an entity (e.g. position). Distinct from src/evidence (evidence pack generation).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class EvidenceType(str, Enum):
    ORIGINAL_IMAGE = "original_image"
    VIDEO_FRAME = "video_frame"
    POSITION_CROP = "position_crop"
    PRODUCT_CROP = "product_crop"
    LABEL_CROP = "label_crop"
    ANNOTATED_IMAGE = "annotated_image"


@dataclass
class Evidence:
    id: str
    entity_type: str
    entity_id: str
    type: EvidenceType
    storage_path: str
    source_asset_id: str
    is_primary: bool
    frame_index: Optional[int] = None
    timestamp_ms: Optional[int] = None
    bbox_json: Optional[Dict[str, Any]] = None
    quality_score: Optional[float] = None
