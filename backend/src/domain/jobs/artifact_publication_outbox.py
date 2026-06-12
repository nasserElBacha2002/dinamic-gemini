"""Durable artifact publication outbox — Phase 3.5."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ArtifactPublicationOutboxStatus(str, Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    PUBLISHED = "published"
    RETRY_SCHEDULED = "retry_scheduled"
    PERMANENTLY_FAILED = "permanently_failed"
    CANCELED = "canceled"


class ArtifactSourceType(str, Enum):
    EXACT_DURABLE_SOURCE = "exact_durable_source"
    EXACT_LOCAL_SOURCE = "exact_local_source"
    RECONSTRUCTABLE = "reconstructable"
    UNAVAILABLE = "unavailable"


@dataclass
class ArtifactPublicationOutboxEntry:
    id: str
    job_id: str
    artifact_kind: str
    required: bool
    source_type: ArtifactSourceType
    source_reference: str | None = None
    destination_key: str | None = None
    content_hash: str | None = None
    size_bytes: int | None = None
    status: ArtifactPublicationOutboxStatus = ArtifactPublicationOutboxStatus.PENDING
    attempt_count: int = 0
    max_attempts: int = 5
    next_attempt_at: datetime | None = None
    claimed_at: datetime | None = None
    claimed_by: str | None = None
    lease_expires_at: datetime | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    published_at: datetime | None = None
    version: int = 1


@dataclass(frozen=True)
class ArtifactPublicationSummary:
    required_total: int
    required_published: int
    pending: int
    retry_scheduled: int
    permanently_failed: int
    next_attempt_at: datetime | None = None
    items: tuple[ArtifactPublicationOutboxEntry, ...] = field(default_factory=tuple)
