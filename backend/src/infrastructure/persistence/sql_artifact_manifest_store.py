"""SQL Server artifact manifest store — Phase 3.3."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from src.application.ports.artifact_manifest_store import ArtifactManifestConcurrencyError
from src.database.sqlserver import SqlServerClient
from src.domain.jobs.artifact_manifest import (
    ArtifactManifestEntry,
    ArtifactManifestStatus,
    ArtifactVerificationLevel,
)
from src.domain.jobs.artifact_policy import ALL_EXPECTED_ARTIFACT_KINDS, REQUIRED_ARTIFACT_KINDS
from src.infrastructure.database.sql_transaction import sql_repository_cursor


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _row_to_entry(row: Any) -> ArtifactManifestEntry:
    required_raw = getattr(row, "required", True)
    required = bool(required_raw) if not isinstance(required_raw, bool) else required_raw
    verification_raw = getattr(row, "verification_level", None)
    verification = (
        ArtifactVerificationLevel(str(verification_raw)) if verification_raw else None
    )
    return ArtifactManifestEntry(
        job_id=str(row.job_id),
        artifact_kind=str(row.artifact_kind),
        required=required,
        storage_key=getattr(row, "storage_key", None),
        source_sha256=getattr(row, "source_sha256", None) or getattr(row, "content_hash", None),
        content_hash=getattr(row, "content_hash", None),
        storage_etag=getattr(row, "storage_etag", None),
        size_bytes=getattr(row, "size_bytes", None),
        status=ArtifactManifestStatus(str(row.status)),
        published_at=_ensure_utc(getattr(row, "published_at", None)),
        verified_at=_ensure_utc(getattr(row, "verified_at", None)),
        verification_level=verification,
        attempt_count=int(getattr(row, "attempt_count", 0) or 0),
        last_error=getattr(row, "last_error", None),
        version=int(getattr(row, "version", 1) or 1),
        created_at=_ensure_utc(getattr(row, "created_at", None)),
        updated_at=_ensure_utc(getattr(row, "updated_at", None)),
    )


class SqlArtifactManifestStore:
    def __init__(self, client: SqlServerClient, *, connection: Any | None = None) -> None:
        self._client = client
        self._connection = connection

    def get_entry(self, job_id: str, artifact_kind: str) -> ArtifactManifestEntry | None:
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                """
                SELECT job_id, artifact_kind, required, storage_key, source_sha256, content_hash,
                       storage_etag, size_bytes, status, published_at, verified_at,
                       verification_level, attempt_count, last_error, version,
                       created_at, updated_at
                FROM job_artifact_manifest
                WHERE job_id = ? AND artifact_kind = ?
                """,
                (job_id, artifact_kind),
            )
            row = cur.fetchone()
            return _row_to_entry(row) if row is not None else None

    def list_entries(self, job_id: str) -> Sequence[ArtifactManifestEntry]:
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                """
                SELECT job_id, artifact_kind, required, storage_key, source_sha256, content_hash,
                       storage_etag, size_bytes, status, published_at, verified_at,
                       verification_level, attempt_count, last_error, version,
                       created_at, updated_at
                FROM job_artifact_manifest
                WHERE job_id = ?
                ORDER BY artifact_kind
                """,
                (job_id,),
            )
            return [_row_to_entry(row) for row in cur.fetchall()]

    def upsert_entry(
        self,
        entry: ArtifactManifestEntry,
        *,
        expected_version: int | None = None,
    ) -> ArtifactManifestEntry:
        existing = self.get_entry(entry.job_id, entry.artifact_kind)
        if existing is None:
            if expected_version is not None:
                raise ArtifactManifestConcurrencyError(
                    f"Manifest create conflict job_id={entry.job_id} kind={entry.artifact_kind}"
                )
        elif expected_version is None or existing.version != expected_version:
            raise ArtifactManifestConcurrencyError(
                f"Manifest version conflict job_id={entry.job_id} kind={entry.artifact_kind}"
            )
        version = 1 if existing is None else existing.version + 1
        now = entry.updated_at or datetime.now(timezone.utc)
        created_at = existing.created_at if existing and existing.created_at else entry.created_at or now
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            if existing is None:
                cur.execute(
                    """
                    INSERT INTO job_artifact_manifest (
                        job_id, artifact_kind, required, storage_key, content_hash, size_bytes,
                        status, published_at, attempt_count, last_error, version,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.job_id,
                        entry.artifact_kind,
                        1 if entry.required else 0,
                        entry.storage_key,
                        entry.content_hash,
                        entry.size_bytes,
                        entry.status.value,
                        entry.published_at,
                        entry.attempt_count or 1,
                        entry.last_error,
                        version,
                        created_at,
                        now,
                    ),
                )
            else:
                cur.execute(
                    """
                    UPDATE job_artifact_manifest
                    SET required = ?, storage_key = ?, content_hash = ?, size_bytes = ?,
                        status = ?, published_at = ?, attempt_count = ?, last_error = ?,
                        version = ?, updated_at = ?
                    WHERE job_id = ? AND artifact_kind = ? AND version = ?
                    """,
                    (
                        1 if entry.required else 0,
                        entry.storage_key,
                        entry.content_hash,
                        entry.size_bytes,
                        entry.status.value,
                        entry.published_at,
                        entry.attempt_count,
                        entry.last_error,
                        version,
                        now,
                        entry.job_id,
                        entry.artifact_kind,
                        expected_version,
                    ),
                )
                if cur.rowcount == 0:
                    raise ArtifactManifestConcurrencyError(
                        f"Manifest version conflict job_id={entry.job_id} kind={entry.artifact_kind}"
                    )
        stored = self.get_entry(entry.job_id, entry.artifact_kind)
        if stored is None:
            raise RuntimeError(
                f"Manifest row missing after upsert job_id={entry.job_id} kind={entry.artifact_kind}"
            )
        return stored

    def ensure_expected_entries(self, job_id: str, *, now: datetime) -> None:
        for kind in ALL_EXPECTED_ARTIFACT_KINDS:
            if self.get_entry(job_id, kind) is None:
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
        existing = self.get_entry(job_id, artifact_kind)
        if existing is None:
            if expected_version is not None:
                raise ArtifactManifestConcurrencyError(
                    f"Manifest create conflict job_id={job_id} kind={artifact_kind}"
                )
        elif expected_version is None or existing.version != expected_version:
            raise ArtifactManifestConcurrencyError(
                f"Manifest version conflict job_id={job_id} kind={artifact_kind}"
            )
        version = 1 if existing is None else existing.version + 1
        created_at = existing.created_at if existing and existing.created_at else now
        attempt = (existing.attempt_count + 1) if existing else 1
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            if existing is None:
                cur.execute(
                    """
                    INSERT INTO job_artifact_manifest (
                        job_id, artifact_kind, required, storage_key, content_hash, size_bytes,
                        status, published_at, attempt_count, last_error, version,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        artifact_kind,
                        1 if required else 0,
                        None,
                        None,
                        None,
                        ArtifactManifestStatus.PENDING.value,
                        None,
                        attempt,
                        None,
                        version,
                        created_at,
                        now,
                    ),
                )
            else:
                cur.execute(
                    """
                    UPDATE job_artifact_manifest
                    SET required = ?, status = ?, attempt_count = ?, version = ?, updated_at = ?
                    WHERE job_id = ? AND artifact_kind = ? AND version = ?
                    """,
                    (
                        1 if required else 0,
                        ArtifactManifestStatus.PENDING.value,
                        attempt,
                        version,
                        now,
                        job_id,
                        artifact_kind,
                        expected_version,
                    ),
                )
        stored = self.get_entry(job_id, artifact_kind)
        if stored is None:
            raise RuntimeError(
                f"Manifest row missing after pending upsert job_id={job_id} kind={artifact_kind}"
            )
        return stored

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
        existing = self.get_entry(job_id, artifact_kind)
        if existing is None:
            if expected_version is not None:
                raise ArtifactManifestConcurrencyError(
                    f"Manifest create conflict job_id={job_id} kind={artifact_kind}"
                )
        elif expected_version is None:
            expected_version = existing.version
        elif existing.version != expected_version:
            raise ArtifactManifestConcurrencyError(
                f"Manifest version conflict job_id={job_id} kind={artifact_kind}"
            )
        version = 1 if existing is None else existing.version + 1
        created_at = existing.created_at if existing and existing.created_at else now
        attempt = (existing.attempt_count + 1) if existing else 1
        sha = source_sha256 or content_hash
        verified = verified_at or now
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            if existing is None:
                cur.execute(
                    """
                    INSERT INTO job_artifact_manifest (
                        job_id, artifact_kind, required, storage_key, source_sha256, content_hash,
                        storage_etag, size_bytes, status, published_at, verified_at,
                        verification_level, attempt_count, last_error, version,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        artifact_kind,
                        1 if required else 0,
                        storage_key,
                        sha,
                        content_hash,
                        storage_etag,
                        size_bytes,
                        ArtifactManifestStatus.PUBLISHED.value,
                        now,
                        verified,
                        verification_level.value if verification_level else None,
                        attempt,
                        None,
                        version,
                        created_at,
                        now,
                    ),
                )
            else:
                params = (
                    1 if required else 0,
                    storage_key,
                    sha,
                    content_hash,
                    storage_etag,
                    size_bytes,
                    ArtifactManifestStatus.PUBLISHED.value,
                    now,
                    verified,
                    verification_level.value if verification_level else None,
                    attempt,
                    version,
                    now,
                    job_id,
                    artifact_kind,
                )
                if expected_version is not None:
                    cur.execute(
                        """
                        UPDATE job_artifact_manifest
                        SET required = ?, storage_key = ?, source_sha256 = ?, content_hash = ?,
                            storage_etag = ?, size_bytes = ?, status = ?, published_at = ?,
                            verified_at = ?, verification_level = ?, attempt_count = ?,
                            version = ?, updated_at = ?
                        WHERE job_id = ? AND artifact_kind = ? AND version = ?
                        """,
                        (*params, expected_version),
                    )
                    if cur.rowcount == 0:
                        raise ArtifactManifestConcurrencyError(
                            f"Manifest version conflict job_id={job_id} kind={artifact_kind}"
                        )
                else:
                    cur.execute(
                        """
                        UPDATE job_artifact_manifest
                        SET required = ?, storage_key = ?, source_sha256 = ?, content_hash = ?,
                            storage_etag = ?, size_bytes = ?, status = ?, published_at = ?,
                            verified_at = ?, verification_level = ?, attempt_count = ?,
                            version = ?, updated_at = ?
                        WHERE job_id = ? AND artifact_kind = ?
                        """,
                        params,
                    )
        stored = self.get_entry(job_id, artifact_kind)
        if stored is None:
            raise RuntimeError(
                f"Manifest row missing after upsert job_id={job_id} kind={artifact_kind}"
            )
        return stored

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
        existing = self.get_entry(job_id, artifact_kind)
        if existing is None:
            if expected_version is not None:
                raise ArtifactManifestConcurrencyError(
                    f"Manifest create conflict job_id={job_id} kind={artifact_kind}"
                )
        elif expected_version is None:
            expected_version = existing.version
        elif existing.version != expected_version:
            raise ArtifactManifestConcurrencyError(
                f"Manifest version conflict job_id={job_id} kind={artifact_kind}"
            )
        version = 1 if existing is None else existing.version + 1
        created_at = existing.created_at if existing and existing.created_at else now
        attempt = (existing.attempt_count + 1) if existing else 1
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            if existing is None:
                cur.execute(
                    """
                    INSERT INTO job_artifact_manifest (
                        job_id, artifact_kind, required, storage_key, content_hash, size_bytes,
                        status, published_at, attempt_count, last_error, version,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        artifact_kind,
                        1 if required else 0,
                        None,
                        None,
                        None,
                        ArtifactManifestStatus.FAILED.value,
                        None,
                        attempt,
                        error[:2048],
                        version,
                        created_at,
                        now,
                    ),
                )
            else:
                cur.execute(
                    """
                    UPDATE job_artifact_manifest
                    SET required = ?, status = ?, attempt_count = ?, last_error = ?,
                        version = ?, updated_at = ?
                    WHERE job_id = ? AND artifact_kind = ?
                    """,
                    (
                        1 if required else 0,
                        ArtifactManifestStatus.FAILED.value,
                        attempt,
                        error[:2048],
                        version,
                        now,
                        job_id,
                        artifact_kind,
                    ),
                )
        stored = self.get_entry(job_id, artifact_kind)
        if stored is None:
            raise RuntimeError(
                f"Manifest row missing after fail upsert job_id={job_id} kind={artifact_kind}"
            )
        return stored

    def required_kinds_published(self, job_id: str) -> bool:
        entries = {entry.artifact_kind: entry for entry in self.list_entries(job_id)}
        return all(
            kind in entries
            and entries[kind].required is True
            and entries[kind].status == ArtifactManifestStatus.PUBLISHED
            for kind in REQUIRED_ARTIFACT_KINDS
        )

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
            e.required and e.status == ArtifactManifestStatus.FAILED for e in self.list_entries(job_id)
        )
