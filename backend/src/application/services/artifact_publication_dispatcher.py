"""Artifact publication dispatcher — Phase 3.5."""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

from src.application.ports.artifact_manifest_store import ArtifactManifestStore
from src.application.ports.artifact_publication_outbox_store import (
    ArtifactPublicationOutboxClaimConflictError,
    ArtifactPublicationOutboxStore,
)
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
from src.domain.jobs.artifact_policy import ALL_EXPECTED_ARTIFACT_KINDS, is_required_artifact_kind
from src.domain.jobs.artifact_publication_outbox import (
    ArtifactPublicationOutboxEntry,
    ArtifactPublicationOutboxStatus,
    ArtifactSourceType,
)
from src.domain.jobs.finalization_evidence import FinalizationStage, StageStatus
from src.infrastructure.pipeline.finalization_stage_recorder import FinalizationStageRecorder
from src.infrastructure.pipeline.job_finalization_tracker import JobFinalizationTracker
from src.infrastructure.pipeline.worker_durable_artifact_publisher import stored_artifact_to_dict
from src.infrastructure.storage.artifact_store import ArtifactStore

logger = logging.getLogger(__name__)


@dataclass
class ArtifactPublicationDispatchResult:
    published_kinds: set[str] = field(default_factory=set)
    retry_scheduled_kinds: set[str] = field(default_factory=set)
    permanently_failed_kinds: set[str] = field(default_factory=set)
    durable_meta: dict[str, dict[str, Any]] = field(default_factory=dict)
    required_complete: bool = False
    continuation_started: bool = False


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
            entry = ArtifactPublicationOutboxEntry(
                id=str(uuid.uuid4()),
                job_id=job_id,
                artifact_kind=kind,
                required=resolved.required,
                source_type=resolved.source_type,
                source_reference=resolved.source_reference,
                destination_key=resolved.destination_key,
                content_hash=resolved.content_hash,
                size_bytes=resolved.size_bytes,
                max_attempts=self._max_attempts,
            )
            stored = self._outbox.ensure_publication_work(entry=entry, now=now)
            logger.info(
                "artifact.outbox.created job_id=%s artifact_kind=%s status=%s",
                job_id,
                kind,
                stored.status.value,
            )

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
        for kind in sorted(ALL_EXPECTED_ARTIFACT_KINDS):
            existing = self._outbox.get_entry(job_id, kind)
            if existing is None:
                continue
            if existing.status == ArtifactPublicationOutboxStatus.PUBLISHED:
                manifest = self._manifest.get_entry(job_id, kind)
                if manifest and manifest.storage_key:
                    result.published_kinds.add(kind)
                    result.durable_meta[kind] = {
                        "storage_key": manifest.storage_key,
                        "file_size_bytes": manifest.size_bytes,
                        "etag": manifest.content_hash,
                    }
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
            logger.info(
                "artifact.publish.claimed job_id=%s artifact_kind=%s attempt_count=%s max_attempts=%s",
                job_id,
                kind,
                claimed.attempt_count,
                claimed.max_attempts,
            )
            self._publish_claimed(
                claimed=claimed,
                run_segment=run_segment,
                run_dir=run_dir,
                source_paths=source_paths,
                result=result,
            )
        result.required_complete = self._manifest.required_kinds_published(job_id)
        if (
            result.required_complete
            and tracker is not None
            and continuation_aisle is not None
            and report_path is not None
            and self._continuation is not None
        ):
            required_stage = self._stage_store.get_stage(job_id, FinalizationStage.REQUIRED_ARTIFACTS)
            if required_stage is None or required_stage.status != StageStatus.COMPLETED:
                tracker.record_artifacts_published(durable_artifacts=result.durable_meta)
            result.continuation_started = self._continuation.continue_if_required_complete(
                job_id=job_id,
                aisle=continuation_aisle,
                report_path=report_path,
                tracker=tracker,
                run_metadata=run_metadata,
                durable_artifacts=result.durable_meta,
            )
            if result.continuation_started:
                logger.info("artifact.required_set.completed job_id=%s", job_id)
        return result

    def _publish_claimed(
        self,
        *,
        claimed: ArtifactPublicationOutboxEntry,
        run_segment: str,
        run_dir: Path,
        source_paths: dict[str, Path] | None,
        result: ArtifactPublicationDispatchResult,
    ) -> None:
        job_id = claimed.job_id
        kind = claimed.artifact_kind
        now = self._clock.now()
        started = time.monotonic()
        logger.info("artifact.publish.started job_id=%s artifact_kind=%s", job_id, kind)
        resolved = resolve_local_source(
            job_id=job_id,
            artifact_kind=kind,
            run_segment=run_segment,
            run_dir=run_dir,
            source_paths=source_paths,
        )
        if resolved.local_path is None:
            if not resolved.required:
                self._outbox.mark_permanently_failed(
                    job_id=job_id,
                    artifact_kind=kind,
                    error_code="optional_source_missing",
                    error_message="Optional artifact source absent",
                    now=now,
                    expected_version=claimed.version,
                )
                return
            self._fail_entry(
                claimed=claimed,
                error_code="source_missing",
                error_message=sanitize_error_message(
                    f"Required source unavailable: {resolved.source_reference}"
                ),
                retryable=False,
                result=result,
            )
            return
        destination_key = resolved.destination_key
        try:
            if self._artifact_store.object_exists(destination_key):
                if resolved.size_bytes is not None:
                    remote_size = self._artifact_store.object_size_bytes(destination_key)
                    if remote_size == resolved.size_bytes:
                        self._mark_confirmed_without_upload(
                            claimed=claimed,
                            destination_key=destination_key,
                            size_bytes=resolved.size_bytes,
                            content_hash=resolved.content_hash,
                            result=result,
                            duration_ms=int((time.monotonic() - started) * 1000),
                        )
                        return
                    self._fail_entry(
                        claimed=claimed,
                        error_code="object_mismatch",
                        error_message=f"Remote size {remote_size} != expected {resolved.size_bytes}",
                        retryable=False,
                        result=result,
                    )
                    return
            with open(resolved.local_path, "rb") as fh:
                stored = self._artifact_store.put_object(
                    destination_key,
                    fh,
                    resolved.content_type,
                )
            if not self._artifact_store.object_exists(destination_key):
                raise RuntimeError("storage_unavailable: object missing after upload")
            remote_size = self._artifact_store.object_size_bytes(destination_key)
            if remote_size != stored.file_size_bytes:
                raise RuntimeError(
                    f"object_mismatch: uploaded size {stored.file_size_bytes} != remote {remote_size}"
                )
            self._manifest.mark_published(
                job_id=job_id,
                artifact_kind=kind,
                storage_key=destination_key,
                size_bytes=stored.file_size_bytes,
                content_hash=stored.etag or resolved.content_hash,
                required=resolved.required,
                now=now,
            )
            self._outbox.mark_published(
                job_id=job_id,
                artifact_kind=kind,
                destination_key=destination_key,
                content_hash=stored.etag or resolved.content_hash,
                size_bytes=stored.file_size_bytes,
                now=now,
                expected_version=claimed.version,
            )
            result.published_kinds.add(kind)
            result.durable_meta[kind] = stored_artifact_to_dict(stored)
            logger.info(
                "artifact.publish.succeeded job_id=%s artifact_kind=%s attempt_count=%s duration_ms=%s",
                job_id,
                kind,
                claimed.attempt_count + 1,
                int((time.monotonic() - started) * 1000),
            )
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

    def _mark_confirmed_without_upload(
        self,
        *,
        claimed: ArtifactPublicationOutboxEntry,
        destination_key: str,
        size_bytes: int | None,
        content_hash: str | None,
        result: ArtifactPublicationDispatchResult,
        duration_ms: int,
    ) -> None:
        now = self._clock.now()
        self._manifest.mark_published(
            job_id=claimed.job_id,
            artifact_kind=claimed.artifact_kind,
            storage_key=destination_key,
            size_bytes=size_bytes,
            content_hash=content_hash,
            required=claimed.required,
            now=now,
        )
        self._outbox.mark_published(
            job_id=claimed.job_id,
            artifact_kind=claimed.artifact_kind,
            destination_key=destination_key,
            content_hash=content_hash,
            size_bytes=size_bytes,
            now=now,
            expected_version=claimed.version,
        )
        result.published_kinds.add(claimed.artifact_kind)
        result.durable_meta[claimed.artifact_kind] = {
            "storage_key": destination_key,
            "file_size_bytes": size_bytes,
            "etag": content_hash,
        }
        logger.info(
            "artifact.publish.succeeded job_id=%s artifact_kind=%s attempt_count=%s duration_ms=%s confirmed_existing=true",
            claimed.job_id,
            claimed.artifact_kind,
            claimed.attempt_count + 1,
            duration_ms,
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
