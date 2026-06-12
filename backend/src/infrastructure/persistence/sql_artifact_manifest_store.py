"""SQL Server artifact manifest store — Phase 3.3."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from src.application.ports.artifact_manifest_store import ArtifactManifestConcurrencyError
from src.database.sqlserver import SqlServerClient
from src.domain.jobs.artifact_manifest import ArtifactManifestEntry, ArtifactManifestStatus
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
    return ArtifactManifestEntry(
        job_id=str(row.job_id),
        artifact_kind=str(row.artifact_kind),
        required=required,
        storage_key=getattr(row, "storage_key", None),
        content_hash=getattr(row, "content_hash", None),
        size_bytes=getattr(row, "size_bytes", None),
        status=ArtifactManifestStatus(str(row.status)),
        published_at=_ensure_utc(getattr(row, "published_at", None)),
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
                SELECT job_id, artifact_kind, required, storage_key, content_hash, size_bytes,
                       status, published_at, attempt_count, last_error, version,
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
                SELECT job_id, artifact_kind, required, storage_key, content_hash, size_bytes,
                       status, published_at, attempt_count, last_error, version,
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
        if entry.status == ArtifactManifestStatus.PUBLISHED and entry.storage_key:
            return self.mark_published(
                job_id=entry.job_id,
                artifact_kind=entry.artifact_kind,
                storage_key=entry.storage_key,
                size_bytes=entry.size_bytes,
                content_hash=entry.content_hash,
                required=entry.required,
                now=entry.updated_at or datetime.now(timezone.utc),
                expected_version=expected_version,
            )
        return self.mark_failed(
            job_id=entry.job_id,
            artifact_kind=entry.artifact_kind,
            required=entry.required,
            error=entry.last_error or "unknown",
            now=entry.updated_at or datetime.now(timezone.utc),
            expected_version=expected_version,
        )

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
        existing = self.get_entry(job_id, artifact_kind)
        version = 1 if existing is None else existing.version + 1
        if expected_version is not None and existing is not None and existing.version != expected_version:
            raise ArtifactManifestConcurrencyError(
                f"Manifest version conflict job_id={job_id} kind={artifact_kind}"
            )
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
                        storage_key,
                        content_hash,
                        size_bytes,
                        ArtifactManifestStatus.PUBLISHED.value,
                        now,
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
                    content_hash,
                    size_bytes,
                    ArtifactManifestStatus.PUBLISHED.value,
                    now,
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
                        SET required = ?, storage_key = ?, content_hash = ?, size_bytes = ?,
                            status = ?, published_at = ?, attempt_count = ?, version = ?,
                            updated_at = ?
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
                        SET required = ?, storage_key = ?, content_hash = ?, size_bytes = ?,
                            status = ?, published_at = ?, attempt_count = ?, version = ?,
                            updated_at = ?
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
        version = 1 if existing is None else existing.version + 1
        if expected_version is not None and existing is not None and existing.version != expected_version:
            raise ArtifactManifestConcurrencyError(
                f"Manifest version conflict job_id={job_id} kind={artifact_kind}"
            )
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
        entries = self.list_entries(job_id)
        required = [e for e in entries if e.required]
        return bool(required) and all(e.status == ArtifactManifestStatus.PUBLISHED for e in required)

    def any_required_failed(self, job_id: str) -> bool:
        return any(
            e.required and e.status == ArtifactManifestStatus.FAILED for e in self.list_entries(job_id)
        )
