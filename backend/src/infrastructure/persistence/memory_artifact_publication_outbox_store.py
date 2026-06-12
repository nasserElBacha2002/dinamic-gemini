"""In-memory artifact publication outbox — Phase 3.5."""

from __future__ import annotations

import copy
import threading
import uuid
from collections.abc import Sequence
from datetime import datetime

from src.application.ports.artifact_publication_outbox_store import (
    ArtifactPublicationOutboxClaimConflictError,
    ArtifactPublicationOutboxConcurrencyError,
    ArtifactPublicationSourceConflictError,
)
from src.domain.jobs.artifact_policy import REQUIRED_ARTIFACT_KINDS
from src.domain.jobs.artifact_publication_outbox import (
    ArtifactPublicationOutboxEntry,
    ArtifactPublicationOutboxStatus,
    ArtifactPublicationSummary,
    ArtifactVerificationLevel,
)


def _key(job_id: str, artifact_kind: str) -> tuple[str, str]:
    return job_id, artifact_kind


def _is_due(entry: ArtifactPublicationOutboxEntry, now: datetime) -> bool:
    if entry.status == ArtifactPublicationOutboxStatus.PENDING:
        return True
    if entry.status == ArtifactPublicationOutboxStatus.RETRY_SCHEDULED:
        return entry.next_attempt_at is None or entry.next_attempt_at <= now
    if entry.status == ArtifactPublicationOutboxStatus.CLAIMED:
        return entry.lease_expires_at is not None and entry.lease_expires_at <= now
    return False


class MemoryArtifactPublicationOutboxStore:
    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], ArtifactPublicationOutboxEntry] = {}
        self._lock = threading.Lock()

    def get_entry(self, job_id: str, artifact_kind: str) -> ArtifactPublicationOutboxEntry | None:
        with self._lock:
            row = self._rows.get(_key(job_id, artifact_kind))
            return copy.deepcopy(row) if row else None

    def list_entries(self, job_id: str) -> Sequence[ArtifactPublicationOutboxEntry]:
        with self._lock:
            return [
                copy.deepcopy(row)
                for key, row in sorted(self._rows.items())
                if key[0] == job_id
            ]

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
        with self._lock:
            existing = self._rows.get(_key(entry.job_id, entry.artifact_kind))
            if existing is not None:
                if existing.status == ArtifactPublicationOutboxStatus.PUBLISHED:
                    return copy.deepcopy(existing)
                new_hash = entry.source_sha256 or entry.content_hash
                old_hash = existing.source_sha256 or existing.content_hash
                if old_hash and new_hash and old_hash != new_hash:
                    raise ArtifactPublicationSourceConflictError(
                        f"Source hash conflict job_id={entry.job_id} kind={entry.artifact_kind}"
                    )
                updated = copy.deepcopy(existing)
                if new_hash:
                    updated.source_sha256 = new_hash
                    updated.content_hash = new_hash
                updated.source_type = entry.source_type
                updated.source_reference = entry.source_reference
                updated.destination_key = entry.destination_key
                updated.size_bytes = entry.size_bytes
                updated.required = entry.required
                updated.updated_at = now
                updated.version += 1
                self._rows[_key(entry.job_id, entry.artifact_kind)] = updated
                return copy.deepcopy(updated)
            source_sha256 = entry.source_sha256 or entry.content_hash
            stored = ArtifactPublicationOutboxEntry(
                id=entry.id or str(uuid.uuid4()),
                job_id=entry.job_id,
                artifact_kind=entry.artifact_kind,
                required=entry.required,
                source_type=entry.source_type,
                source_reference=entry.source_reference,
                destination_key=entry.destination_key,
                source_sha256=source_sha256,
                content_hash=source_sha256,
                size_bytes=entry.size_bytes,
                status=ArtifactPublicationOutboxStatus.PENDING,
                attempt_count=0,
                max_attempts=entry.max_attempts,
                created_at=now,
                updated_at=now,
                version=1,
            )
            self._rows[_key(entry.job_id, entry.artifact_kind)] = stored
            return copy.deepcopy(stored)

    def claim_due_entries(
        self,
        *,
        claimed_by: str,
        lease_expires_at: datetime,
        now: datetime,
        limit: int,
    ) -> Sequence[ArtifactPublicationOutboxEntry]:
        claimed: list[ArtifactPublicationOutboxEntry] = []
        with self._lock:
            for key in sorted(self._rows.keys()):
                if len(claimed) >= limit:
                    break
                existing = self._rows[key]
                if not _is_due(existing, now):
                    continue
                if existing.status == ArtifactPublicationOutboxStatus.PUBLISHED:
                    continue
                if existing.status == ArtifactPublicationOutboxStatus.PERMANENTLY_FAILED:
                    continue
                if existing.status == ArtifactPublicationOutboxStatus.CANCELED:
                    continue
                updated = copy.deepcopy(existing)
                updated.status = ArtifactPublicationOutboxStatus.CLAIMED
                updated.claimed_at = now
                updated.claimed_by = claimed_by
                updated.lease_expires_at = lease_expires_at
                updated.updated_at = now
                updated.version += 1
                self._rows[key] = updated
                claimed.append(copy.deepcopy(updated))
        return claimed

    def claim_entry(
        self,
        *,
        job_id: str,
        artifact_kind: str,
        claimed_by: str,
        lease_expires_at: datetime,
        now: datetime,
    ) -> ArtifactPublicationOutboxEntry:
        with self._lock:
            existing = self._rows.get(_key(job_id, artifact_kind))
            if existing is None:
                raise ArtifactPublicationOutboxClaimConflictError(
                    f"No outbox row job_id={job_id} kind={artifact_kind}"
                )
            if not _is_due(existing, now):
                raise ArtifactPublicationOutboxClaimConflictError("Not eligible")
            if existing.status == ArtifactPublicationOutboxStatus.PUBLISHED:
                raise ArtifactPublicationOutboxClaimConflictError("Already published")
            if existing.status == ArtifactPublicationOutboxStatus.PERMANENTLY_FAILED:
                raise ArtifactPublicationOutboxClaimConflictError("Permanently failed")
            updated = copy.deepcopy(existing)
            updated.status = ArtifactPublicationOutboxStatus.CLAIMED
            updated.claimed_at = now
            updated.claimed_by = claimed_by
            updated.lease_expires_at = lease_expires_at
            updated.updated_at = now
            updated.version += 1
            self._rows[_key(job_id, artifact_kind)] = updated
            return copy.deepcopy(updated)

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
        return self._transition(
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
            clear_claim=True,
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
        return self._transition(
            job_id,
            artifact_kind,
            expected_version=expected_version,
            now=now,
            status=ArtifactPublicationOutboxStatus.RETRY_SCHEDULED,
            next_attempt_at=next_attempt_at,
            last_error_code=error_code,
            last_error_message=error_message,
            clear_claim=True,
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
        return self._transition(
            job_id,
            artifact_kind,
            expected_version=expected_version,
            now=now,
            status=ArtifactPublicationOutboxStatus.PERMANENTLY_FAILED,
            last_error_code=error_code,
            last_error_message=error_message,
            clear_claim=True,
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
        return self._transition(
            job_id,
            artifact_kind,
            expected_version=expected_version,
            now=now,
            status=ArtifactPublicationOutboxStatus.PENDING,
            next_attempt_at=None,
            last_error_code=None,
            last_error_message=None,
            clear_claim=True,
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
        return self._transition(
            job_id,
            artifact_kind,
            expected_version=expected_version,
            now=now,
            status=ArtifactPublicationOutboxStatus.RETRY_SCHEDULED,
            next_attempt_at=now,
            clear_claim=True,
            increment_attempt=False,
        )

    def release_expired_claims(self, *, now: datetime) -> int:
        released = 0
        with self._lock:
            for key, existing in list(self._rows.items()):
                if existing.status != ArtifactPublicationOutboxStatus.CLAIMED:
                    continue
                if existing.lease_expires_at and existing.lease_expires_at <= now:
                    updated = copy.deepcopy(existing)
                    updated.status = (
                        ArtifactPublicationOutboxStatus.RETRY_SCHEDULED
                        if updated.attempt_count > 0
                        else ArtifactPublicationOutboxStatus.PENDING
                    )
                    updated.claimed_at = None
                    updated.claimed_by = None
                    updated.lease_expires_at = None
                    updated.updated_at = now
                    updated.version += 1
                    self._rows[key] = updated
                    released += 1
        return released

    def summary_for_job(self, job_id: str) -> ArtifactPublicationSummary:
        entries = list(self.list_entries(job_id))
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

    def _transition(
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
        clear_claim: bool = False,
        increment_attempt: bool = False,
    ) -> ArtifactPublicationOutboxEntry:
        with self._lock:
            existing = self._rows.get(_key(job_id, artifact_kind))
            if existing is None or existing.version != expected_version:
                raise ArtifactPublicationOutboxConcurrencyError(
                    f"Outbox version conflict job_id={job_id} kind={artifact_kind}"
                )
            updated = copy.deepcopy(existing)
            updated.status = status
            if destination_key is not None:
                updated.destination_key = destination_key
            if source_sha256 is not None:
                updated.source_sha256 = source_sha256
            if content_hash is not None:
                updated.content_hash = content_hash
            if storage_etag is not None:
                updated.storage_etag = storage_etag
            if storage_checksum_value is not None:
                updated.storage_checksum_value = storage_checksum_value
            if storage_checksum_algorithm is not None:
                updated.storage_checksum_algorithm = storage_checksum_algorithm
            if size_bytes is not None:
                updated.size_bytes = size_bytes
            if published_at is not None:
                updated.published_at = published_at
            if verified_at is not None:
                updated.verified_at = verified_at
            if verification_level is not None:
                updated.verification_level = verification_level
            if next_attempt_at is not None:
                updated.next_attempt_at = next_attempt_at
            if last_error_code is not None:
                updated.last_error_code = last_error_code
            if last_error_message is not None:
                updated.last_error_message = last_error_message
            if clear_claim:
                updated.claimed_at = None
                updated.claimed_by = None
                updated.lease_expires_at = None
            if increment_attempt:
                updated.attempt_count += 1
            updated.updated_at = now
            updated.version += 1
            self._rows[_key(job_id, artifact_kind)] = updated
            return copy.deepcopy(updated)
