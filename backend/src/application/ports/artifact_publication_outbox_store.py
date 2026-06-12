"""Port for durable artifact publication outbox — Phase 3.5."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol, runtime_checkable

from src.domain.jobs.artifact_publication_outbox import (
    ArtifactPublicationOutboxEntry,
    ArtifactPublicationSummary,
    ArtifactSourceType,
)


class ArtifactPublicationOutboxConcurrencyError(Exception):
    pass


class ArtifactPublicationOutboxClaimConflictError(Exception):
    pass


@runtime_checkable
class ArtifactPublicationOutboxStore(Protocol):
    def get_entry(self, job_id: str, artifact_kind: str) -> ArtifactPublicationOutboxEntry | None: ...

    def list_entries(self, job_id: str) -> Sequence[ArtifactPublicationOutboxEntry]: ...

    def ensure_publication_work(
        self,
        *,
        entry: ArtifactPublicationOutboxEntry,
        now: datetime,
    ) -> ArtifactPublicationOutboxEntry: ...

    def claim_entry(
        self,
        *,
        job_id: str,
        artifact_kind: str,
        claimed_by: str,
        lease_expires_at: datetime,
        now: datetime,
    ) -> ArtifactPublicationOutboxEntry: ...

    def mark_published(
        self,
        *,
        job_id: str,
        artifact_kind: str,
        destination_key: str,
        content_hash: str | None,
        size_bytes: int | None,
        now: datetime,
        expected_version: int,
    ) -> ArtifactPublicationOutboxEntry: ...

    def mark_retry_scheduled(
        self,
        *,
        job_id: str,
        artifact_kind: str,
        next_attempt_at: datetime,
        error_code: str,
        error_message: str,
        now: datetime,
        expected_version: int,
    ) -> ArtifactPublicationOutboxEntry: ...

    def mark_permanently_failed(
        self,
        *,
        job_id: str,
        artifact_kind: str,
        error_code: str,
        error_message: str,
        now: datetime,
        expected_version: int,
    ) -> ArtifactPublicationOutboxEntry: ...

    def release_expired_claims(self, *, now: datetime) -> int: ...

    def summary_for_job(self, job_id: str) -> ArtifactPublicationSummary: ...

    def reset_retryable(
        self,
        *,
        job_id: str,
        artifact_kind: str,
        now: datetime,
        expected_version: int,
    ) -> ArtifactPublicationOutboxEntry: ...
