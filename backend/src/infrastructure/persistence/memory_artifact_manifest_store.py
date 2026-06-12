"""In-memory artifact manifest store — Phase 3.3."""

from __future__ import annotations

import copy
from collections.abc import Sequence
from datetime import datetime

from src.application.ports.artifact_manifest_store import ArtifactManifestConcurrencyError
from src.domain.jobs.artifact_manifest import ArtifactManifestEntry, ArtifactManifestStatus


def _key(job_id: str, kind: str) -> tuple[str, str]:
    return job_id, kind


class MemoryArtifactManifestStore:
    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], ArtifactManifestEntry] = {}

    def get_entry(self, job_id: str, artifact_kind: str) -> ArtifactManifestEntry | None:
        row = self._rows.get(_key(job_id, artifact_kind))
        return copy.deepcopy(row) if row is not None else None

    def list_entries(self, job_id: str) -> Sequence[ArtifactManifestEntry]:
        rows = [copy.deepcopy(r) for r in self._rows.values() if r.job_id == job_id]
        rows.sort(key=lambda r: r.artifact_kind)
        return rows

    def upsert_entry(
        self,
        entry: ArtifactManifestEntry,
        *,
        expected_version: int | None = None,
    ) -> ArtifactManifestEntry:
        k = _key(entry.job_id, entry.artifact_kind)
        existing = self._rows.get(k)
        if expected_version is not None and (
            existing is None or existing.version != expected_version
        ):
            raise ArtifactManifestConcurrencyError(
                f"Manifest version conflict job_id={entry.job_id} kind={entry.artifact_kind}"
            )
        stored = copy.deepcopy(entry)
        self._rows[k] = stored
        return copy.deepcopy(stored)

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
    ) -> ArtifactManifestEntry:
        existing = self._rows.get(_key(job_id, artifact_kind))
        version = 1 if existing is None else existing.version + 1
        if expected_version is not None and existing is not None and existing.version != expected_version:
            raise ArtifactManifestConcurrencyError(
                f"Manifest version conflict job_id={job_id} kind={artifact_kind}"
            )
        entry = ArtifactManifestEntry(
            job_id=job_id,
            artifact_kind=artifact_kind,
            required=required,
            storage_key=storage_key,
            content_hash=content_hash,
            size_bytes=size_bytes,
            status=ArtifactManifestStatus.PUBLISHED,
            published_at=now,
            attempt_count=(existing.attempt_count + 1) if existing else 1,
            last_error=None,
            version=version,
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        self._rows[_key(job_id, artifact_kind)] = copy.deepcopy(entry)
        return copy.deepcopy(entry)

    def mark_failed(
        self,
        *,
        job_id: str,
        artifact_kind: str,
        required: bool,
        error: str,
        now: datetime,
        expected_version: int | None = None,
    ) -> ArtifactManifestEntry:
        existing = self._rows.get(_key(job_id, artifact_kind))
        version = 1 if existing is None else existing.version + 1
        if expected_version is not None and existing is not None and existing.version != expected_version:
            raise ArtifactManifestConcurrencyError(
                f"Manifest version conflict job_id={job_id} kind={artifact_kind}"
            )
        entry = ArtifactManifestEntry(
            job_id=job_id,
            artifact_kind=artifact_kind,
            required=required,
            storage_key=existing.storage_key if existing else None,
            content_hash=existing.content_hash if existing else None,
            size_bytes=existing.size_bytes if existing else None,
            status=ArtifactManifestStatus.FAILED,
            published_at=existing.published_at if existing else None,
            attempt_count=(existing.attempt_count + 1) if existing else 1,
            last_error=error[:2048],
            version=version,
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        self._rows[_key(job_id, artifact_kind)] = copy.deepcopy(entry)
        return copy.deepcopy(entry)

    def required_kinds_published(self, job_id: str) -> bool:
        required = [r for r in self._rows.values() if r.job_id == job_id and r.required]
        return bool(required) and all(
            r.status == ArtifactManifestStatus.PUBLISHED for r in required
        )

    def any_required_failed(self, job_id: str) -> bool:
        return any(
            r.job_id == job_id and r.required and r.status == ArtifactManifestStatus.FAILED
            for r in self._rows.values()
        )
