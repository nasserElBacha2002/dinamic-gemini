"""Artifact publication dispatcher — Phase 3.5 corrections."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import closing
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any, BinaryIO

from src.application.ports.artifact_manifest_store import (
    ArtifactManifestConcurrencyError,
    ArtifactManifestStore,
)
from src.application.ports.artifact_publication_outbox_store import (
    ArtifactPublicationOutboxClaimConflictError,
    ArtifactPublicationOutboxConcurrencyError,
    ArtifactPublicationOutboxStore,
)
from src.application.ports.artifact_staging_store import ArtifactStagingStore
from src.application.ports.clock import Clock
from src.application.ports.finalization_stage_store import FinalizationStageStore
from src.application.services.artifact_finalization_continuation import (
    ArtifactFinalizationContinuationCoordinator,
)
from src.application.services.artifact_publication_retry_policy import (
    classify_publication_error,
    compute_next_attempt_at,
    sanitize_error_message,
)
from src.application.services.artifact_publication_source_policy import resolve_local_source
from src.application.services.artifact_publication_state_reconciler import (
    ArtifactPublicationStateReconciler,
)
from src.application.services.artifact_publication_verifier import verify_remote_object
from src.application.services.automatic_finalization_continuation_use_case import (
    AutomaticFinalizationContinuationUseCase,
)
from src.domain.jobs.artifact_manifest import ArtifactVerificationLevel as ManifestVerificationLevel
from src.domain.jobs.artifact_policy import (
    ALL_EXPECTED_ARTIFACT_KINDS,
    ARTIFACT_KIND_EXECUTION_LOG,
    ARTIFACT_KIND_HYBRID_REPORT_CSV,
    ARTIFACT_KIND_HYBRID_REPORT_JSON,
    is_required_artifact_kind,
)
from src.domain.jobs.artifact_publication_outbox import (
    ArtifactPublicationOutboxEntry,
    ArtifactPublicationOutboxStatus,
    ArtifactSourceType,
    ArtifactVerificationLevel,
)
from src.infrastructure.pipeline.finalization_stage_recorder import FinalizationStageRecorder
from src.infrastructure.pipeline.job_finalization_tracker import JobFinalizationTracker
from src.infrastructure.pipeline.worker_durable_artifact_publisher import stored_artifact_to_dict
from src.infrastructure.storage.artifact_store import ArtifactStore

logger = logging.getLogger(__name__)

WORKER_ARTIFACT_PUBLISH_ORDER: tuple[str, ...] = (
    ARTIFACT_KIND_EXECUTION_LOG,
    ARTIFACT_KIND_HYBRID_REPORT_JSON,
    ARTIFACT_KIND_HYBRID_REPORT_CSV,
)

_REQUIRED_DURABLE_KINDS = frozenset({ARTIFACT_KIND_EXECUTION_LOG, ARTIFACT_KIND_HYBRID_REPORT_JSON})


class ArtifactSourceStagingFailedError(Exception):
    """Required artifact bytes could not be staged durably."""


@dataclass
class ArtifactPublicationDispatchResult:
    published_kinds: set[str] = field(default_factory=set)
    retry_scheduled_kinds: set[str] = field(default_factory=set)
    permanently_failed_kinds: set[str] = field(default_factory=set)
    durable_meta: dict[str, dict[str, Any]] = field(default_factory=dict)
    required_complete: bool = False
    continuation_started: bool = False
    claimed_count: int = 0


class ArtifactPublicationDispatcher:
    def __init__(
        self,
        *,
        outbox_store: ArtifactPublicationOutboxStore,
        manifest_store: ArtifactManifestStore,
        stage_store: FinalizationStageStore,
        artifact_store: ArtifactStore,
        stage_recorder: FinalizationStageRecorder | None,
        continuation: ArtifactFinalizationContinuationCoordinator | None,
        automatic_continuation: AutomaticFinalizationContinuationUseCase | None,
        staging_store: ArtifactStagingStore | None,
        reconciler: ArtifactPublicationStateReconciler | None,
        clock: Clock,
        lease_seconds: int = 120,
        max_attempts: int = 5,
        backoff_seconds: tuple[int, ...] = (0, 30, 120, 600, 1800),
        claimed_by_prefix: str = "artifact-dispatcher",
    ) -> None:
        self._outbox = outbox_store
        self._manifest = manifest_store
        self._stage_store = stage_store
        self._artifact_store = artifact_store
        self._stage_recorder = stage_recorder
        self._continuation = continuation
        self._automatic_continuation = automatic_continuation
        self._staging = staging_store
        self._reconciler = reconciler
        self._clock = clock
        self._lease_seconds = lease_seconds
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds
        self._claimed_by_prefix = claimed_by_prefix

    def register_publication_work(
        self,
        *,
        job_id: str,
        run_segment: str,
        run_dir: Path,
        source_paths: dict[str, Path] | None = None,
    ) -> None:
        now = self._clock.now()
        self._manifest.ensure_expected_entries(job_id, now=now)
        for kind in sorted(ALL_EXPECTED_ARTIFACT_KINDS):
            resolved = resolve_local_source(
                job_id=job_id,
                artifact_kind=kind,
                run_segment=run_segment,
                run_dir=run_dir,
                source_paths=source_paths,
            )
            if not resolved.required and resolved.local_path is None:
                continue
            entry = self._build_outbox_entry(
                job_id=job_id,
                kind=kind,
                resolved=resolved,
            )
            stored = self._outbox.ensure_publication_work(entry=entry, now=now)
            logger.info(
                "artifact.outbox.created job_id=%s artifact_kind=%s status=%s source_type=%s",
                job_id,
                kind,
                stored.status.value,
                stored.source_type.value,
            )

    def _build_outbox_entry(
        self,
        *,
        job_id: str,
        kind: str,
        resolved,
    ) -> ArtifactPublicationOutboxEntry:
        if kind in _REQUIRED_DURABLE_KINDS:
            if resolved.local_path is None or not resolved.local_path.is_file():
                raise ArtifactSourceStagingFailedError(
                    f"Required source missing for staging: {kind} job_id={job_id}"
                )
            if self._staging is None:
                raise ArtifactSourceStagingFailedError("Staging store not configured")
            with open(resolved.local_path, "rb") as fh:
                staged = self._staging.put_exact_source(
                    job_id=job_id,
                    artifact_kind=kind,
                    file_obj=fh,
                )
            return ArtifactPublicationOutboxEntry(
                id=str(uuid.uuid4()),
                job_id=job_id,
                artifact_kind=kind,
                required=resolved.required,
                source_type=ArtifactSourceType.EXACT_DURABLE_SOURCE,
                source_reference=staged.staging_key,
                destination_key=resolved.destination_key,
                source_sha256=staged.source_sha256,
                content_hash=staged.source_sha256,
                size_bytes=staged.size_bytes,
                max_attempts=self._max_attempts,
            )
        return ArtifactPublicationOutboxEntry(
            id=str(uuid.uuid4()),
            job_id=job_id,
            artifact_kind=kind,
            required=resolved.required,
            source_type=resolved.source_type,
            source_reference=resolved.source_reference,
            destination_key=resolved.destination_key,
            source_sha256=resolved.content_hash,
            content_hash=resolved.content_hash,
            size_bytes=resolved.size_bytes,
            max_attempts=self._max_attempts,
        )

    def process_due_batch(self, *, limit: int) -> ArtifactPublicationDispatchResult:
        self._outbox.release_expired_claims(now=self._clock.now())
        now = self._clock.now()
        claimed = self._outbox.claim_due_entries(
            claimed_by=f"{self._claimed_by_prefix}:{uuid.uuid4().hex[:8]}",
            lease_expires_at=now + timedelta(seconds=self._lease_seconds),
            now=now,
            limit=limit,
        )
        result = ArtifactPublicationDispatchResult(claimed_count=len(claimed))
        touched_jobs: set[str] = set()
        for entry in claimed:
            touched_jobs.add(entry.job_id)
            self._publish_claimed(claimed=entry, result=result)
        for job_id in touched_jobs:
            result.required_complete = result.required_complete or self._manifest.required_kinds_published(
                job_id
            )
            if self._manifest.required_kinds_published(job_id):
                if self._try_automatic_continuation(job_id, result):
                    result.continuation_started = True
        return result

    def dispatch_job(
        self,
        *,
        job_id: str,
        run_segment: str,
        run_dir: Path,
        tracker: JobFinalizationTracker | None = None,
        continuation_aisle=None,
        report_path: Path | None = None,
        run_metadata: dict[str, Any] | None = None,
        source_paths: dict[str, Path] | None = None,
    ) -> ArtifactPublicationDispatchResult:
        self._outbox.release_expired_claims(now=self._clock.now())
        result = ArtifactPublicationDispatchResult()
        now = self._clock.now()
        inline_worker = tracker is not None
        for kind in WORKER_ARTIFACT_PUBLISH_ORDER:
            existing = self._outbox.get_entry(job_id, kind)
            if existing is None:
                continue
            if existing.status == ArtifactPublicationOutboxStatus.PUBLISHED:
                self._collect_published_meta(job_id, kind, result)
                continue
            if existing.status == ArtifactPublicationOutboxStatus.PERMANENTLY_FAILED:
                if is_required_artifact_kind(kind):
                    result.permanently_failed_kinds.add(kind)
                continue
            if existing.status == ArtifactPublicationOutboxStatus.RETRY_SCHEDULED:
                if existing.next_attempt_at and existing.next_attempt_at > now:
                    if is_required_artifact_kind(kind):
                        result.retry_scheduled_kinds.add(kind)
                    continue
            if self._reconciler is not None:
                self._reconciler.reconcile_entry(job_id=job_id, artifact_kind=kind)
                refreshed = self._outbox.get_entry(job_id, kind)
                if refreshed and refreshed.status == ArtifactPublicationOutboxStatus.PUBLISHED:
                    self._collect_published_meta(job_id, kind, result)
                    continue
            try:
                claimed = self._outbox.claim_entry(
                    job_id=job_id,
                    artifact_kind=kind,
                    claimed_by=f"{self._claimed_by_prefix}:{uuid.uuid4().hex[:8]}",
                    lease_expires_at=now + timedelta(seconds=self._lease_seconds),
                    now=now,
                )
            except ArtifactPublicationOutboxClaimConflictError:
                continue
            self._publish_claimed(
                claimed=claimed,
                run_segment=run_segment,
                run_dir=run_dir,
                source_paths=source_paths,
                result=result,
            )
            if (
                inline_worker
                and kind in result.permanently_failed_kinds
                and is_required_artifact_kind(kind)
            ):
                break
        result.required_complete = self._manifest.required_kinds_published(job_id)
        if (
            result.required_complete
            and not inline_worker
            and self._try_automatic_continuation(job_id, result)
        ):
            result.continuation_started = True
        return result

    def _try_automatic_continuation(
        self,
        job_id: str,
        result: ArtifactPublicationDispatchResult,
    ) -> bool:
        if self._automatic_continuation is None:
            return False
        cont = self._automatic_continuation.continue_finalization(job_id)
        if cont.completed:
            logger.info("artifact.required_set.completed job_id=%s source=automatic", job_id)
            return True
        if cont.reason:
            logger.debug(
                "artifact.automatic_continuation.skipped job_id=%s reason=%s",
                job_id,
                cont.reason,
            )
        return False

    def _collect_published_meta(
        self,
        job_id: str,
        kind: str,
        result: ArtifactPublicationDispatchResult,
    ) -> None:
        manifest = self._manifest.get_entry(job_id, kind)
        if manifest and manifest.storage_key:
            result.published_kinds.add(kind)
            result.durable_meta[kind] = {
                "storage_key": manifest.storage_key,
                "file_size_bytes": manifest.size_bytes,
                "etag": manifest.storage_etag or manifest.content_hash,
                "source_sha256": manifest.source_sha256,
            }

    def _publish_claimed(
        self,
        *,
        claimed: ArtifactPublicationOutboxEntry,
        run_segment: str | None = None,
        run_dir: Path | None = None,
        source_paths: dict[str, Path] | None = None,
        result: ArtifactPublicationDispatchResult,
    ) -> None:
        job_id = claimed.job_id
        kind = claimed.artifact_kind
        now = self._clock.now()
        started = time.monotonic()
        logger.info("artifact.publish.started job_id=%s artifact_kind=%s", job_id, kind)
        try:
            content_type, source_sha256, size_bytes, source_handle = self._resolve_source(
                claimed=claimed,
                run_segment=run_segment,
                run_dir=run_dir,
                source_paths=source_paths,
            )
        except FileNotFoundError as exc:
            if not claimed.required:
                self._outbox.mark_permanently_failed(
                    job_id=job_id,
                    artifact_kind=kind,
                    error_code="optional_source_missing",
                    error_message=sanitize_error_message(str(exc)),
                    now=now,
                    expected_version=claimed.version,
                )
                return
            self._fail_entry(
                claimed=claimed,
                error_code="source_missing",
                error_message=sanitize_error_message(str(exc)),
                retryable=False,
                result=result,
            )
            return

        destination_key = claimed.destination_key
        if not destination_key:
            self._fail_entry(
                claimed=claimed,
                error_code="invalid_destination_key",
                error_message="Missing destination key",
                retryable=False,
                result=result,
            )
            return

        try:
            if self._artifact_store.object_exists(destination_key):
                level, metadata = verify_remote_object(
                    artifact_store=self._artifact_store,
                    destination_key=destination_key,
                    expected_sha256=source_sha256 or "",
                    expected_size=size_bytes,
                )
                if level == ArtifactVerificationLevel.CONFIRMED:
                    self._mark_published_pair(
                        claimed=claimed,
                        destination_key=destination_key,
                        source_sha256=source_sha256,
                        size_bytes=metadata.file_size_bytes if metadata else size_bytes,
                        storage_etag=metadata.etag if metadata else None,
                        storage_checksum_value=metadata.checksum_value if metadata else None,
                        storage_checksum_algorithm=metadata.checksum_algorithm if metadata else None,
                        verification_level=level,
                        result=result,
                        duration_ms=int((time.monotonic() - started) * 1000),
                        confirmed_existing=True,
                    )
                    return
                if level == ArtifactVerificationLevel.POSITIVE_EVIDENCE_ONLY:
                    self._fail_entry(
                        claimed=claimed,
                        error_code="object_unverified",
                        error_message="Remote object matches size only; SHA-256 not confirmed",
                        retryable=True,
                        result=result,
                    )
                    return
            if source_handle is None:
                raise FileNotFoundError("Source handle unavailable for upload")
            with closing(source_handle):
                stored = self._artifact_store.put_object(destination_key, source_handle, content_type)
            if not self._artifact_store.object_exists(destination_key):
                raise RuntimeError("storage_unavailable: object missing after upload")
            level, metadata = verify_remote_object(
                artifact_store=self._artifact_store,
                destination_key=destination_key,
                expected_sha256=source_sha256 or "",
                expected_size=stored.file_size_bytes,
            )
            if level != ArtifactVerificationLevel.CONFIRMED:
                raise RuntimeError("checksum_mismatch: uploaded object not SHA-256 confirmed")
            self._mark_published_pair(
                claimed=claimed,
                destination_key=destination_key,
                source_sha256=source_sha256,
                size_bytes=stored.file_size_bytes,
                storage_etag=stored.etag or (metadata.etag if metadata else None),
                storage_checksum_value=metadata.checksum_value if metadata else None,
                storage_checksum_algorithm=metadata.checksum_algorithm if metadata else None,
                verification_level=level,
                result=result,
                duration_ms=int((time.monotonic() - started) * 1000),
                stored=stored,
            )
        except ArtifactManifestConcurrencyError:
            self._handle_manifest_write_failure(claimed=claimed, result=result)
        except ArtifactPublicationOutboxConcurrencyError:
            if self._reconciler is not None:
                self._reconciler.reconcile_entry(job_id=job_id, artifact_kind=kind)
        except Exception as exc:
            error_code, retryable = classify_publication_error(exc)
            self._fail_entry(
                claimed=claimed,
                error_code=error_code,
                error_message=sanitize_error_message(str(exc)),
                retryable=retryable,
                result=result,
                duration_ms=int((time.monotonic() - started) * 1000),
            )

    def _resolve_source(
        self,
        *,
        claimed: ArtifactPublicationOutboxEntry,
        run_segment: str | None,
        run_dir: Path | None,
        source_paths: dict[str, Path] | None,
    ) -> tuple[str, str | None, int | None, BinaryIO | None]:
        if claimed.source_type == ArtifactSourceType.EXACT_DURABLE_SOURCE:
            if self._staging is None or not claimed.source_reference:
                raise FileNotFoundError("Durable staging reference missing")
            if not self._staging.source_exists(claimed.source_reference):
                raise FileNotFoundError(f"Staged source missing: {claimed.source_reference}")
            resolved = resolve_local_source(
                job_id=claimed.job_id,
                artifact_kind=claimed.artifact_kind,
                run_segment=run_segment or "",
                run_dir=run_dir or Path("."),
            )
            handle = self._staging.open_source(claimed.source_reference)
            return (
                resolved.content_type,
                claimed.source_sha256 or self._staging.source_checksum(claimed.source_reference),
                claimed.size_bytes or self._staging.source_size(claimed.source_reference),
                handle,
            )
        if run_dir is None:
            raise FileNotFoundError("Local run_dir unavailable for source resolution")
        resolved = resolve_local_source(
            job_id=claimed.job_id,
            artifact_kind=claimed.artifact_kind,
            run_segment=run_segment or "",
            run_dir=run_dir,
            source_paths=source_paths,
        )
        if resolved.local_path is None:
            raise FileNotFoundError(
                f"Required source unavailable: {resolved.source_reference}"
            )
        return (
            resolved.content_type,
            resolved.content_hash,
            resolved.size_bytes,
            open(resolved.local_path, "rb"),
        )

    def _mark_published_pair(
        self,
        *,
        claimed: ArtifactPublicationOutboxEntry,
        destination_key: str,
        source_sha256: str | None,
        size_bytes: int | None,
        storage_etag: str | None,
        storage_checksum_value: str | None,
        storage_checksum_algorithm: str | None,
        verification_level: ArtifactVerificationLevel,
        result: ArtifactPublicationDispatchResult,
        duration_ms: int,
        confirmed_existing: bool = False,
        stored=None,
    ) -> None:
        now = self._clock.now()
        self._manifest.mark_published(
            job_id=claimed.job_id,
            artifact_kind=claimed.artifact_kind,
            storage_key=destination_key,
            size_bytes=size_bytes,
            content_hash=source_sha256,
            required=claimed.required,
            now=now,
            source_sha256=source_sha256,
            storage_etag=storage_etag,
            verified_at=now,
            verification_level=ManifestVerificationLevel(verification_level.value),
        )
        try:
            self._outbox.mark_published(
                job_id=claimed.job_id,
                artifact_kind=claimed.artifact_kind,
                destination_key=destination_key,
                source_sha256=source_sha256,
                size_bytes=size_bytes,
                storage_etag=storage_etag,
                storage_checksum_value=storage_checksum_value,
                storage_checksum_algorithm=storage_checksum_algorithm,
                verification_level=verification_level,
                verified_at=now,
                now=now,
                expected_version=claimed.version,
            )
        except ArtifactPublicationOutboxConcurrencyError:
            if self._reconciler is not None:
                self._reconciler.reconcile_entry(
                    job_id=claimed.job_id,
                    artifact_kind=claimed.artifact_kind,
                )
        result.published_kinds.add(claimed.artifact_kind)
        if stored is not None:
            result.durable_meta[claimed.artifact_kind] = stored_artifact_to_dict(stored)
        else:
            result.durable_meta[claimed.artifact_kind] = {
                "storage_key": destination_key,
                "file_size_bytes": size_bytes,
                "etag": storage_etag,
                "source_sha256": source_sha256,
            }
        logger.info(
            "artifact.publish.succeeded job_id=%s artifact_kind=%s attempt_count=%s duration_ms=%s confirmed_existing=%s",
            claimed.job_id,
            claimed.artifact_kind,
            claimed.attempt_count + 1,
            duration_ms,
            confirmed_existing,
        )

    def _handle_manifest_write_failure(
        self,
        *,
        claimed: ArtifactPublicationOutboxEntry,
        result: ArtifactPublicationDispatchResult,
    ) -> None:
        logger.warning(
            "artifact.publish.manifest_cas_failed job_id=%s artifact_kind=%s",
            claimed.job_id,
            claimed.artifact_kind,
        )
        if self._reconciler is not None:
            self._reconciler.reconcile_entry(
                job_id=claimed.job_id,
                artifact_kind=claimed.artifact_kind,
            )

    def _fail_entry(
        self,
        *,
        claimed: ArtifactPublicationOutboxEntry,
        error_code: str,
        error_message: str,
        retryable: bool,
        result: ArtifactPublicationDispatchResult,
        duration_ms: int | None = None,
    ) -> None:
        now = self._clock.now()
        next_attempt = claimed.attempt_count + 1
        if retryable and next_attempt < claimed.max_attempts:
            next_at = compute_next_attempt_at(
                attempt_count=next_attempt,
                now=now,
                backoff_seconds=self._backoff_seconds,
            )
            self._outbox.mark_retry_scheduled(
                job_id=claimed.job_id,
                artifact_kind=claimed.artifact_kind,
                next_attempt_at=next_at,
                error_code=error_code,
                error_message=error_message,
                now=now,
                expected_version=claimed.version,
            )
            if claimed.required:
                result.retry_scheduled_kinds.add(claimed.artifact_kind)
            logger.warning(
                "artifact.publish.retry_scheduled job_id=%s artifact_kind=%s attempt_count=%s max_attempts=%s next_attempt_at=%s error_code=%s duration_ms=%s",
                claimed.job_id,
                claimed.artifact_kind,
                next_attempt,
                claimed.max_attempts,
                next_at.isoformat(),
                error_code,
                duration_ms,
            )
            return
        self._outbox.mark_permanently_failed(
            job_id=claimed.job_id,
            artifact_kind=claimed.artifact_kind,
            error_code=error_code,
            error_message=error_message,
            now=now,
            expected_version=claimed.version,
        )
        if claimed.required:
            self._manifest.mark_failed(
                job_id=claimed.job_id,
                artifact_kind=claimed.artifact_kind,
                required=True,
                error=error_code,
                now=now,
            )
            result.permanently_failed_kinds.add(claimed.artifact_kind)
        logger.error(
            "artifact.publish.permanently_failed job_id=%s artifact_kind=%s attempt_count=%s error_code=%s duration_ms=%s",
            claimed.job_id,
            claimed.artifact_kind,
            next_attempt,
            error_code,
            duration_ms,
        )
