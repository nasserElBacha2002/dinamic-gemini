"""
Evidence domain entity — v3.0 (Documento técnico §7.6).

Visual evidence linked to an entity (e.g. position). Distinct from src/evidence (evidence pack generation).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


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
    is_primary: bool
    source_asset_id: str | None = None
    frame_index: int | None = None
    timestamp_ms: int | None = None
    bbox_json: dict[str, Any] | None = None
    quality_score: float | None = None
    # storage_path: legacy-relative path; storage_key: canonical ArtifactStore key when using a provider.
    storage_provider: str | None = None
    storage_bucket: str | None = None
    storage_key: str | None = None
    # HTTP/storage Content-Type for this artifact (no separate mime_type on Evidence).
    content_type: str | None = None
    file_size_bytes: int | None = None
    etag: str | None = None
