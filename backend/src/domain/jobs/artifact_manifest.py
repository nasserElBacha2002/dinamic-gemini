"""Durable artifact manifest entries — Phase 3.3."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ArtifactManifestStatus(str, Enum):
    PENDING = "pending"
    PUBLISHED = "published"
    FAILED = "failed"
    UNKNOWN = "unknown"


class ArtifactVerificationLevel(str, Enum):
    CONFIRMED = "confirmed"
    POSITIVE_EVIDENCE_ONLY = "positive_evidence_only"
    UNVERIFIABLE = "unverifiable"


@dataclass
class ArtifactManifestEntry:
    job_id: str
    artifact_kind: str
    required: bool
    storage_key: str | None = None
    source_sha256: str | None = None
    content_hash: str | None = None  # legacy; may hold etag
    storage_etag: str | None = None
    size_bytes: int | None = None
    status: ArtifactManifestStatus = ArtifactManifestStatus.PENDING
    published_at: datetime | None = None
    verified_at: datetime | None = None
    verification_level: ArtifactVerificationLevel | None = None
    attempt_count: int = 0
    last_error: str | None = None
    version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None
