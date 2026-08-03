"""Durable rendered positioning label artifact metadata."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class AisleLocationLabelArtifactStatus(str, Enum):
    PENDING = "PENDING"
    RENDERING = "RENDERING"
    READY = "READY"
    FAILED = "FAILED"


@dataclass
class AisleLocationLabelArtifact:
    id: str
    label_id: str
    format: str
    preset: str
    template_version: int
    marker_version: int
    storage_provider: str
    storage_bucket: str | None
    storage_key: str | None
    content_type: str
    file_size_bytes: int
    artifact_hash: str
    created_at: datetime
    status: AisleLocationLabelArtifactStatus = AisleLocationLabelArtifactStatus.READY
    failure_code: str | None = None
    failure_detail: str | None = None
    updated_at: datetime | None = None
    render_owner: str | None = None
