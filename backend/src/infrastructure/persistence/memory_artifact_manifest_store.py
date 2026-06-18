"""In-memory artifact manifest store — Phase 3.3."""

from __future__ import annotations

import copy
from collections.abc import Sequence
from datetime import datetime

from src.application.ports.artifact_manifest_store import ArtifactManifestConcurrencyError
from src.domain.jobs.artifact_manifest import (
    ArtifactManifestEntry,
    ArtifactManifestStatus,
    ArtifactVerificationLevel,
)
from src.domain.jobs.artifact_policy import ALL_EXPECTED_ARTIFACT_KINDS, REQUIRED_ARTIFACT_KINDS


def _key(job_id: str, kind: str) -> tuple[str, str]:
    return job_id, kind


def _assert_cas(
    *,
    existing: ArtifactManifestEntry | None,
    expected_version: int | None,
    job_id: str,
    artifact_kind: str,
) -> None:
    if existing is None:
        if expected_version is not None:
            raise ArtifactManifestConcurrencyError(
                f"Manifest create conflict job_id={job_id} kind={artifact_kind}"
            )
        return
    if expected_version is None or existing.version != expected_version:
        raise ArtifactManifestConcurrencyError(
            f"Manifest version conflict job_id={job_id} kind={artifact_kind}"
        )


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
        _assert_cas(
            existing=existing,
            expected_version=expected_version,
            job_id=entry.job_id,
            artifact_kind=entry.artifact_kind,
        )
        version = 1 if existing is None else existing.version + 1
        stored = copy.deepcopy(entry)
        stored.version = version
        stored.created_at = existing.created_at if existing and existing.created_at else entry.created_at
        self._rows[k] = stored
        return copy.deepcopy(stored)

    def ensure_expected_entries(self, job_id: str, *, now: datetime) -> None:
        for kind in ALL_EXPECTED_ARTIFACT_KINDS:
            if self._rows.get(_key(job_id, kind)) is None:
                self.mark_pending(
                    job_id=job_id,
                    artifact_kind=kind,
                    required=kind in REQUIRED_ARTIFACT_KINDS,
                    now=now,
                    expected_version=None,
                )

    def mark_pending(
        self,
        *,
        job_id: str,
        artifact_kind: str,
        required: bool,
        now: datetime,
        expected_version: int | None = None,
    ) -> ArtifactManifestEntry:
        existing = self._rows.get(_key(job_id, artifact_kind))
        _assert_cas(
            existing=existing,
            expected_version=expected_version,
            job_id=job_id,
            artifact_kind=artifact_kind,
        )
        version = 1 if existing is None else existing.version + 1
        entry = ArtifactManifestEntry(
            job_id=job_id,
            artifact_kind=artifact_kind,
            required=required,
            storage_key=existing.storage_key if existing else None,
            content_hash=existing.content_hash if existing else None,
            size_bytes=existing.size_bytes if existing else None,
            status=ArtifactManifestStatus.PENDING,
            published_at=None,
            attempt_count=(existing.attempt_count + 1) if existing else 1,
            last_error=None,
            version=version,
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        self._rows[_key(job_id, artifact_kind)] = copy.deepcopy(entry)
        return copy.deepcopy(entry)

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
        source_sha256: str | None = None,
        storage_etag: str | None = None,
        verified_at: datetime | None = None,
        verification_level: ArtifactVerificationLevel | None = None,
    ) -> ArtifactManifestEntry:
        existing = self._rows.get(_key(job_id, artifact_kind))
        if expected_version is None and existing is not None:
            expected_version = existing.version
        _assert_cas(
            existing=existing,
            expected_version=expected_version,
            job_id=job_id,
            artifact_kind=artifact_kind,
        )
        version = 1 if existing is None else existing.version + 1
        entry = ArtifactManifestEntry(
            job_id=job_id,
            artifact_kind=artifact_kind,
            required=required,
            storage_key=storage_key,
            source_sha256=source_sha256 or content_hash,
            content_hash=content_hash,
            storage_etag=storage_etag,
            size_bytes=size_bytes,
            status=ArtifactManifestStatus.PUBLISHED,
            published_at=now,
            verified_at=verified_at or now,
            verification_level=verification_level,
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
        if expected_version is None and existing is not None:
            expected_version = existing.version
        _assert_cas(
            existing=existing,
            expected_version=expected_version,
            job_id=job_id,
            artifact_kind=artifact_kind,
        )
        version = 1 if existing is None else existing.version + 1
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
        entries = [e for e in self.list_entries(job_id) if e.required]
        if not entries:
            return False
        return all(e.status == ArtifactManifestStatus.PUBLISHED for e in entries)

    def missing_required_kinds(self, job_id: str) -> set[str]:
        entries = {entry.artifact_kind: entry for entry in self.list_entries(job_id)}
        missing: set[str] = set()
        for kind in REQUIRED_ARTIFACT_KINDS:
            entry = entries.get(kind)
            if (
                entry is None
                or not entry.required
                or entry.status != ArtifactManifestStatus.PUBLISHED
            ):
                missing.add(kind)
        return missing

    def any_required_failed(self, job_id: str) -> bool:
        return any(
            r.job_id == job_id and r.required and r.status == ArtifactManifestStatus.FAILED
            for r in self._rows.values()
        )
