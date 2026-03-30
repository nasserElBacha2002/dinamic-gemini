"""
SourceAsset domain entity — v3.0 (Documento técnico §7.3).

Raw input (photo or video) associated with an aisle.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class SourceAssetType(str, Enum):
    PHOTO = "photo"
    VIDEO = "video"


@dataclass
class SourceAsset:
    id: str
    aisle_id: str
    type: SourceAssetType
    original_filename: str
    storage_path: str
    mime_type: str
    uploaded_at: datetime
    metadata_json: Optional[Dict[str, Any]] = None
    # Phase 1 S3 foundation (optional during rollout; legacy records may be path-only).
    storage_provider: Optional[str] = None
    storage_bucket: Optional[str] = None
    storage_key: Optional[str] = None
    content_type: Optional[str] = None
    file_size_bytes: Optional[int] = None
    etag: Optional[str] = None
