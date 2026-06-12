"""Port for durable artifact manifest entries — Phase 3.3."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol, runtime_checkable

from src.domain.jobs.artifact_manifest import ArtifactManifestEntry, ArtifactManifestStatus


class ArtifactManifestConcurrencyError(Exception):
    pass


@runtime_checkable
class ArtifactManifestStore(Protocol):
    def get_entry(self, job_id: str, artifact_kind: str) -> ArtifactManifestEntry | None: ...

    def list_entries(self, job_id: str) -> Sequence[ArtifactManifestEntry]: ...

    def upsert_entry(
        self,
        entry: ArtifactManifestEntry,
        *,
        expected_version: int | None = None,
    ) -> ArtifactManifestEntry: ...

    def mark_published(
        self,
        *,
        job_id: str,
        artifact_kind: str,
        storage_key: str,
        size_bytes: int | None,
        content_hash: str | None,
        required: bool,
        now: datetime,
        expected_version: int | None = None,
    ) -> ArtifactManifestEntry: ...

    def mark_failed(
        self,
        *,
        job_id: str,
        artifact_kind: str,
        required: bool,
        error: str,
        now: datetime,
        expected_version: int | None = None,
    ) -> ArtifactManifestEntry: ...

    def required_kinds_published(self, job_id: str) -> bool: ...

    def any_required_failed(self, job_id: str) -> bool: ...
