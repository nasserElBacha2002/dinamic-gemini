"""SQL Server artifact publication outbox — Phase 3.5."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from src.application.ports.artifact_publication_outbox_store import (
    ArtifactPublicationOutboxClaimConflictError,
    ArtifactPublicationOutboxConcurrencyError,
    ArtifactPublicationSourceConflictError,
    MissingMigrationOrStoreUnavailableError,
)
from src.database.sqlserver import SqlServerClient
from src.domain.jobs.artifact_policy import REQUIRED_ARTIFACT_KINDS
from src.domain.jobs.artifact_publication_outbox import (
    ArtifactPublicationOutboxEntry,
    ArtifactPublicationOutboxStatus,
    ArtifactPublicationSummary,
    ArtifactSourceType,
    ArtifactVerificationLevel,
)
from src.infrastructure.database.sql_transaction import sql_repository_cursor

_SELECT_COLUMNS = """
    id, job_id, artifact_kind, required, source_type, source_reference,
    destination_key, source_sha256, content_hash, storage_etag,
    storage_checksum_value, storage_checksum_algorithm, size_bytes, status,
    attempt_count, max_attempts, next_attempt_at, claimed_at, claimed_by,
    lease_expires_at, last_error_code, last_error_message, created_at,
    updated_at, published_at, verified_at, verification_level, version
"""


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _row_to_entry(row: Any) -> ArtifactPublicationOutboxEntry:
    required_raw = getattr(row, "required", True)
    required = bool(required_raw) if not isinstance(required_raw, bool) else required_raw
    verification_raw = getattr(row, "verification_level", None)
    verification = (
        ArtifactVerificationLevel(str(verification_raw)) if verification_raw else None
    )
    source_sha256 = getattr(row, "source_sha256", None) or getattr(row, "content_hash", None)
    return ArtifactPublicationOutboxEntry(
        id=str(row.id),
        job_id=str(row.job_id),
        artifact_kind=str(row.artifact_kind),
        required=required,
        source_type=ArtifactSourceType(str(row.source_type)),
        source_reference=getattr(row, "source_reference", None),
        destination_key=getattr(row, "destination_key", None),
        source_sha256=source_sha256,
        content_hash=getattr(row, "content_hash", None),
        storage_etag=getattr(row, "storage_etag", None),
        storage_checksum_value=getattr(row, "storage_checksum_value", None),
        storage_checksum_algorithm=getattr(row, "storage_checksum_algorithm", None),
        size_bytes=getattr(row, "size_bytes", None),
        status=ArtifactPublicationOutboxStatus(str(row.status)),
        attempt_count=int(getattr(row, "attempt_count", 0) or 0),
        max_attempts=int(getattr(row, "max_attempts", 5) or 5),
        next_attempt_at=_ensure_utc(getattr(row, "next_attempt_at", None)),
        claimed_at=_ensure_utc(getattr(row, "claimed_at", None)),
        claimed_by=getattr(row, "claimed_by", None),
        lease_expires_at=_ensure_utc(getattr(row, "lease_expires_at", None)),
        last_error_code=getattr(row, "last_error_code", None),
        last_error_message=getattr(row, "last_error_message", None),
        created_at=_ensure_utc(getattr(row, "created_at", None)),
        updated_at=_ensure_utc(getattr(row, "updated_at", None)),
        published_at=_ensure_utc(getattr(row, "published_at", None)),
        verified_at=_ensure_utc(getattr(row, "verified_at", None)),
        verification_level=verification,
        version=int(getattr(row, "version", 1) or 1),
    )


def _store_unavailable(exc: BaseException) -> bool:
    message = str(exc).lower()
    markers = (
        "invalid object name",
        "artifact_publication_outbox",
        "does not exist",
        "no such table",
    )
    return any(marker in message for marker in markers)


class SqlArtifactPublicationOutboxStore:
    def __init__(self, client: SqlServerClient, *, connection: Any | None = None) -> None:
        self._client = client
        self._connection = connection

    def get_entry(self, job_id: str, artifact_kind: str) -> ArtifactPublicationOutboxEntry | None:
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                f"""
                SELECT {_SELECT_COLUMNS}
                FROM artifact_publication_outbox
                WHERE job_id = ? AND artifact_kind = ?
                """,
                (job_id, artifact_kind),
            )
            row = cur.fetchone()
            return _row_to_entry(row) if row else None

    def list_entries(self, job_id: str) -> Sequence[ArtifactPublicationOutboxEntry]:
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                f"""
                SELECT {_SELECT_COLUMNS}
                FROM artifact_publication_outbox
                WHERE job_id = ?
                ORDER BY artifact_kind
                """,
                (job_id,),
            )
            return [_row_to_entry(row) for row in cur.fetchall()]

    def has_active_retryable_work(self, job_id: str, *, now: datetime) -> bool:
        _ = now
        for row in self.list_entries(job_id):
            if row.status in (
                ArtifactPublicationOutboxStatus.PENDING,
                ArtifactPublicationOutboxStatus.RETRY_SCHEDULED,
                ArtifactPublicationOutboxStatus.CLAIMED,
            ):
                return True
        return False

    def ensure_publication_work(
        self,
        *,
        entry: ArtifactPublicationOutboxEntry,
        now: datetime,
    ) -> ArtifactPublicationOutboxEntry:
        existing = self.get_entry(entry.job_id, entry.artifact_kind)
        if existing is not None:
            if existing.status == ArtifactPublicationOutboxStatus.PUBLISHED:
                return existing
            new_hash = entry.source_sha256 or entry.content_hash
            old_hash = existing.source_sha256 or existing.content_hash
            if old_hash and new_hash and old_hash != new_hash:
                raise ArtifactPublicationSourceConflictError(
                    f"Source hash conflict job_id={entry.job_id} kind={entry.artifact_kind}"
                )
            with sql_repository_cursor(self._client, connection=self._connection) as cur:
                cur.execute(
                    """
                    UPDATE artifact_publication_outbox
                    SET source_type = ?, source_reference = ?, destination_key = ?,
                        source_sha256 = COALESCE(?, source_sha256),
                        content_hash = COALESCE(?, content_hash),
                        size_bytes = ?, required = ?,
                        updated_at = ?, version = version + 1
                    WHERE job_id = ? AND artifact_kind = ? AND version = ?
                    """,
                    (
                        entry.source_type.value,
                        entry.source_reference,
                        entry.destination_key,
                        new_hash,
                        new_hash,
                        entry.size_bytes,
                        entry.required,
                        now.replace(tzinfo=None),
                        entry.job_id,
                        entry.artifact_kind,
                        existing.version,
                    ),
                )
                if cur.rowcount != 1:
                    raise ArtifactPublicationOutboxConcurrencyError(
                        f"Outbox update conflict job_id={entry.job_id} kind={entry.artifact_kind}"
                    )
            updated = self.get_entry(entry.job_id, entry.artifact_kind)
            assert updated is not None
            return updated
        row_id = entry.id or str(uuid.uuid4())
        source_sha256 = entry.source_sha256 or entry.content_hash
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                """
                INSERT INTO artifact_publication_outbox (
                    id, job_id, artifact_kind, required, source_type, source_reference,
                    destination_key, source_sha256, content_hash, size_bytes, status,
                    attempt_count, max_attempts, created_at, updated_at, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row_id,
                    entry.job_id,
                    entry.artifact_kind,
                    entry.required,
                    entry.source_type.value,
                    entry.source_reference,
                    entry.destination_key,
                    source_sha256,
                    source_sha256,
                    entry.size_bytes,
                    ArtifactPublicationOutboxStatus.PENDING.value,
                    0,
                    entry.max_attempts,
                    now.replace(tzinfo=None),
                    now.replace(tzinfo=None),
                    1,
                ),
            )
        created = self.get_entry(entry.job_id, entry.artifact_kind)
        assert created is not None
        return created

    def claim_due_entries(
        self,
        *,
        claimed_by: str,
        lease_expires_at: datetime,
        now: datetime,
        limit: int,
    ) -> Sequence[ArtifactPublicationOutboxEntry]:
        now_naive = now.replace(tzinfo=None)
        lease_naive = lease_expires_at.replace(tzinfo=None)
        output_cols = ", ".join(
            f"INSERTED.{col.strip()}"
            for col in _SELECT_COLUMNS.replace("\n", " ").split(",")
        )
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                f"""
                ;WITH due AS (
                    SELECT TOP (?) id
                    FROM artifact_publication_outbox WITH (UPDLOCK, READPAST, ROWLOCK)
                    WHERE (
                        status = ?
                        OR (status = ? AND (next_attempt_at IS NULL OR next_attempt_at <= ?))
                        OR (status = ? AND lease_expires_at IS NOT NULL AND lease_expires_at <= ?)
                    )
                    ORDER BY COALESCE(next_attempt_at, created_at), job_id, artifact_kind
                )
                UPDATE o
                SET status = ?, claimed_at = ?, claimed_by = ?, lease_expires_at = ?,
                    updated_at = ?, version = o.version + 1
                OUTPUT {output_cols}
                FROM artifact_publication_outbox o
                INNER JOIN due d ON o.id = d.id
                """,
                (
                    limit,
                    ArtifactPublicationOutboxStatus.PENDING.value,
                    ArtifactPublicationOutboxStatus.RETRY_SCHEDULED.value,
                    now_naive,
                    ArtifactPublicationOutboxStatus.CLAIMED.value,
                    now_naive,
                    ArtifactPublicationOutboxStatus.CLAIMED.value,
                    now_naive,
                    claimed_by,
                    lease_naive,
                    now_naive,
                ),
            )
            rows = cur.fetchall()
        return [_row_to_entry(row) for row in rows]

    def claim_entry(
        self,
        *,
        job_id: str,
        artifact_kind: str,
        claimed_by: str,
        lease_expires_at: datetime,
        now: datetime,
    ) -> ArtifactPublicationOutboxEntry:
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                f"""
                SELECT {_SELECT_COLUMNS}
                FROM artifact_publication_outbox WITH (UPDLOCK, ROWLOCK)
                WHERE job_id = ? AND artifact_kind = ?
                """,
                (job_id, artifact_kind),
            )
            row = cur.fetchone()
            if row is None:
                raise ArtifactPublicationOutboxClaimConflictError(
                    f"No outbox row job_id={job_id} kind={artifact_kind}"
                )
            existing = _row_to_entry(row)
            if existing.status == ArtifactPublicationOutboxStatus.PUBLISHED:
                raise ArtifactPublicationOutboxClaimConflictError("Already published")
            if existing.status == ArtifactPublicationOutboxStatus.PERMANENTLY_FAILED:
                raise ArtifactPublicationOutboxClaimConflictError("Permanently failed")
            if existing.status == ArtifactPublicationOutboxStatus.CANCELED:
                raise ArtifactPublicationOutboxClaimConflictError("Canceled")
            if existing.status == ArtifactPublicationOutboxStatus.CLAIMED:
                if existing.lease_expires_at and existing.lease_expires_at > now:
                    raise ArtifactPublicationOutboxClaimConflictError("Active lease")
            if existing.status == ArtifactPublicationOutboxStatus.RETRY_SCHEDULED:
                if existing.next_attempt_at and existing.next_attempt_at > now:
                    raise ArtifactPublicationOutboxClaimConflictError("Not yet eligible")
            cur.execute(
                """
                UPDATE artifact_publication_outbox
                SET status = ?, claimed_at = ?, claimed_by = ?, lease_expires_at = ?,
                    updated_at = ?, version = version + 1
                WHERE job_id = ? AND artifact_kind = ? AND version = ?
                """,
                (
                    ArtifactPublicationOutboxStatus.CLAIMED.value,
                    now.replace(tzinfo=None),
                    claimed_by,
                    lease_expires_at.replace(tzinfo=None),
                    now.replace(tzinfo=None),
                    job_id,
                    artifact_kind,
                    existing.version,
                ),
            )
            if cur.rowcount != 1:
                raise ArtifactPublicationOutboxConcurrencyError(
                    f"Outbox claim conflict job_id={job_id} kind={artifact_kind}"
                )
        claimed = self.get_entry(job_id, artifact_kind)
        assert claimed is not None
        return claimed

    def mark_published(
        self,
        *,
        job_id: str,
        artifact_kind: str,
        destination_key: str,
        source_sha256: str | None,
        size_bytes: int | None,
        storage_etag: str | None,
        storage_checksum_value: str | None,
        storage_checksum_algorithm: str | None,
        verification_level: ArtifactVerificationLevel,
        verified_at: datetime,
        now: datetime,
        expected_version: int,
    ) -> ArtifactPublicationOutboxEntry:
        return self._finish(
            job_id,
            artifact_kind,
            expected_version=expected_version,
            now=now,
            status=ArtifactPublicationOutboxStatus.PUBLISHED,
            destination_key=destination_key,
            source_sha256=source_sha256,
            content_hash=source_sha256,
            storage_etag=storage_etag,
            storage_checksum_value=storage_checksum_value,
            storage_checksum_algorithm=storage_checksum_algorithm,
            size_bytes=size_bytes,
            published_at=now,
            verified_at=verified_at,
            verification_level=verification_level,
            increment_attempt=True,
        )

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
    ) -> ArtifactPublicationOutboxEntry:
        return self._finish(
            job_id,
            artifact_kind,
            expected_version=expected_version,
            now=now,
            status=ArtifactPublicationOutboxStatus.RETRY_SCHEDULED,
            next_attempt_at=next_attempt_at,
            last_error_code=error_code,
            last_error_message=error_message,
            increment_attempt=True,
        )

    def mark_permanently_failed(
        self,
        *,
        job_id: str,
        artifact_kind: str,
        error_code: str,
        error_message: str,
        now: datetime,
        expected_version: int,
    ) -> ArtifactPublicationOutboxEntry:
        return self._finish(
            job_id,
            artifact_kind,
            expected_version=expected_version,
            now=now,
            status=ArtifactPublicationOutboxStatus.PERMANENTLY_FAILED,
            last_error_code=error_code,
            last_error_message=error_message,
            increment_attempt=True,
        )

    def reset_retryable(
        self,
        *,
        job_id: str,
        artifact_kind: str,
        now: datetime,
        expected_version: int,
    ) -> ArtifactPublicationOutboxEntry:
        return self._finish(
            job_id,
            artifact_kind,
            expected_version=expected_version,
            now=now,
            status=ArtifactPublicationOutboxStatus.PENDING,
            next_attempt_at=None,
            last_error_code=None,
            last_error_message=None,
            increment_attempt=False,
        )

    def retry_now(
        self,
        *,
        job_id: str,
        artifact_kind: str,
        now: datetime,
        expected_version: int,
    ) -> ArtifactPublicationOutboxEntry:
        return self._finish(
            job_id,
            artifact_kind,
            expected_version=expected_version,
            now=now,
            status=ArtifactPublicationOutboxStatus.RETRY_SCHEDULED,
            next_attempt_at=now,
            increment_attempt=False,
        )

    def release_expired_claims(self, *, now: datetime) -> int:
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                """
                UPDATE artifact_publication_outbox
                SET status = CASE WHEN attempt_count > 0 THEN ? ELSE ? END,
                    claimed_at = NULL, claimed_by = NULL, lease_expires_at = NULL,
                    updated_at = ?, version = version + 1
                WHERE status = ? AND lease_expires_at IS NOT NULL AND lease_expires_at <= ?
                """,
                (
                    ArtifactPublicationOutboxStatus.RETRY_SCHEDULED.value,
                    ArtifactPublicationOutboxStatus.PENDING.value,
                    now.replace(tzinfo=None),
                    ArtifactPublicationOutboxStatus.CLAIMED.value,
                    now.replace(tzinfo=None),
                ),
            )
            return int(cur.rowcount or 0)

    def summary_for_job(self, job_id: str) -> ArtifactPublicationSummary:
        try:
            entries = list(self.list_entries(job_id))
        except Exception as exc:
            if _store_unavailable(exc):
                raise MissingMigrationOrStoreUnavailableError(str(exc)) from exc
            raise
        required_total = len(REQUIRED_ARTIFACT_KINDS)
        required_published = sum(
            1
            for e in entries
            if e.required and e.status == ArtifactPublicationOutboxStatus.PUBLISHED
        )
        pending = sum(1 for e in entries if e.status == ArtifactPublicationOutboxStatus.PENDING)
        retry_scheduled = sum(
            1 for e in entries if e.status == ArtifactPublicationOutboxStatus.RETRY_SCHEDULED
        )
        permanently_failed = sum(
            1 for e in entries if e.status == ArtifactPublicationOutboxStatus.PERMANENTLY_FAILED
        )
        next_times = [e.next_attempt_at for e in entries if e.next_attempt_at is not None]
        next_attempt_at = min(next_times) if next_times else None
        return ArtifactPublicationSummary(
            required_total=required_total,
            required_published=required_published,
            pending=pending,
            retry_scheduled=retry_scheduled,
            permanently_failed=permanently_failed,
            next_attempt_at=next_attempt_at,
            items=tuple(entries),
        )

    def _finish(
        self,
        job_id: str,
        artifact_kind: str,
        *,
        expected_version: int,
        now: datetime,
        status: ArtifactPublicationOutboxStatus,
        destination_key: str | None = None,
        source_sha256: str | None = None,
        content_hash: str | None = None,
        storage_etag: str | None = None,
        storage_checksum_value: str | None = None,
        storage_checksum_algorithm: str | None = None,
        size_bytes: int | None = None,
        published_at: datetime | None = None,
        verified_at: datetime | None = None,
        verification_level: ArtifactVerificationLevel | None = None,
        next_attempt_at: datetime | None = None,
        last_error_code: str | None = None,
        last_error_message: str | None = None,
        increment_attempt: bool = False,
    ) -> ArtifactPublicationOutboxEntry:
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                """
                UPDATE artifact_publication_outbox
                SET status = ?, destination_key = COALESCE(?, destination_key),
                    source_sha256 = COALESCE(?, source_sha256),
                    content_hash = COALESCE(?, content_hash),
                    storage_etag = COALESCE(?, storage_etag),
                    storage_checksum_value = COALESCE(?, storage_checksum_value),
                    storage_checksum_algorithm = COALESCE(?, storage_checksum_algorithm),
                    size_bytes = COALESCE(?, size_bytes),
                    published_at = COALESCE(?, published_at),
                    verified_at = COALESCE(?, verified_at),
                    verification_level = COALESCE(?, verification_level),
                    next_attempt_at = ?,
                    last_error_code = ?,
                    last_error_message = ?,
                    claimed_at = NULL, claimed_by = NULL, lease_expires_at = NULL,
                    attempt_count = attempt_count + ?,
                    updated_at = ?, version = version + 1
                WHERE job_id = ? AND artifact_kind = ? AND version = ?
                """,
                (
                    status.value,
                    destination_key,
                    source_sha256,
                    content_hash,
                    storage_etag,
                    storage_checksum_value,
                    storage_checksum_algorithm,
                    size_bytes,
                    published_at.replace(tzinfo=None) if published_at else None,
                    verified_at.replace(tzinfo=None) if verified_at else None,
                    verification_level.value if verification_level else None,
                    next_attempt_at.replace(tzinfo=None) if next_attempt_at else None,
                    last_error_code,
                    last_error_message,
                    1 if increment_attempt else 0,
                    now.replace(tzinfo=None),
                    job_id,
                    artifact_kind,
                    expected_version,
                ),
            )
            if cur.rowcount != 1:
                raise ArtifactPublicationOutboxConcurrencyError(
                    f"Outbox finish conflict job_id={job_id} kind={artifact_kind}"
                )
        updated = self.get_entry(job_id, artifact_kind)
        assert updated is not None
        return updated
