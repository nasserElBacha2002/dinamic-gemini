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
    # Phase 1+ S3: storage_path is legacy display/local-relative path under v3_uploads.
    # storage_key is the canonical logical ArtifactStore key; when storage_provider is set,
    # resolution must use storage_key (+ bucket) and must not infer key from storage_path.
    storage_provider: Optional[str] = None
    storage_bucket: Optional[str] = None
    storage_key: Optional[str] = None
    # Object storage Content-Type metadata (may match mime_type after upload).
    content_type: Optional[str] = None
    file_size_bytes: Optional[int] = None
    etag: Optional[str] = None
