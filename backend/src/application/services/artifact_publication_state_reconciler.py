"""Reconcile manifest/outbox split writes after crash windows — Phase 3.5 corrections."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.application.ports.artifact_manifest_store import (
    ArtifactManifestConcurrencyError,
    ArtifactManifestStore,
)
from src.application.ports.artifact_publication_outbox_store import (
    ArtifactPublicationOutboxConcurrencyError,
    ArtifactPublicationOutboxStore,
)
from src.application.ports.clock import Clock
from src.application.services.artifact_publication_verifier import verify_remote_object
from src.domain.jobs.artifact_manifest import ArtifactManifestStatus
from src.domain.jobs.artifact_publication_outbox import (
    ArtifactPublicationOutboxStatus,
    ArtifactVerificationLevel,
)
from src.infrastructure.storage.artifact_store import ArtifactStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReconciliationOutcome:
    manifest_repaired: bool = False
    outbox_repaired: bool = False
    inconsistency_detected: bool = False


class ArtifactPublicationStateReconciler:
    """Repair manifest/outbox divergence when durable storage already holds the object."""

    def __init__(
        self,
        *,
        outbox_store: ArtifactPublicationOutboxStore,
        manifest_store: ArtifactManifestStore,
        artifact_store: ArtifactStore,
        clock: Clock,
    ) -> None:
        self._outbox = outbox_store
        self._manifest = manifest_store
        self._artifact_store = artifact_store
        self._clock = clock

    def reconcile_entry(self, *, job_id: str, artifact_kind: str) -> ReconciliationOutcome:
        outbox = self._outbox.get_entry(job_id, artifact_kind)
        manifest = self._manifest.get_entry(job_id, artifact_kind)
        if outbox is None:
            return ReconciliationOutcome()

        destination_key = outbox.destination_key or (manifest.storage_key if manifest else None)
        source_sha256 = outbox.source_sha256 or outbox.content_hash
        if destination_key is None or source_sha256 is None:
            return ReconciliationOutcome()

        level, metadata = verify_remote_object(
            artifact_store=self._artifact_store,
            destination_key=destination_key,
            expected_sha256=source_sha256,
            expected_size=outbox.size_bytes,
        )
        if level != ArtifactVerificationLevel.CONFIRMED:
            if (
                manifest is not None
                and manifest.status == ArtifactManifestStatus.PUBLISHED
                and outbox.status == ArtifactPublicationOutboxStatus.PUBLISHED
                and not self._artifact_store.object_exists(destination_key)
            ):
                logger.error(
                    "artifact.reconcile.inconsistent job_id=%s artifact_kind=%s destination_key=%s",
                    job_id,
                    artifact_kind,
                    destination_key,
                )
                return ReconciliationOutcome(inconsistency_detected=True)
            return ReconciliationOutcome()

        now = self._clock.now()
        outcome = ReconciliationOutcome()
        verified_at = now
        storage_etag = metadata.etag if metadata else None
        checksum_value = metadata.checksum_value if metadata else None
        checksum_algorithm = metadata.checksum_algorithm if metadata else None
        size_bytes = metadata.file_size_bytes if metadata else outbox.size_bytes

        manifest_published = manifest is not None and manifest.status == ArtifactManifestStatus.PUBLISHED
        outbox_published = outbox.status == ArtifactPublicationOutboxStatus.PUBLISHED

        if not manifest_published:
            try:
                self._manifest.mark_published(
                    job_id=job_id,
                    artifact_kind=artifact_kind,
                    storage_key=destination_key,
                    size_bytes=size_bytes,
                    content_hash=source_sha256,
                    required=outbox.required,
                    now=now,
                    expected_version=manifest.version if manifest else None,
                    source_sha256=source_sha256,
                    storage_etag=storage_etag,
                    verified_at=verified_at,
                    verification_level=level,
                )
                outcome = ReconciliationOutcome(
                    manifest_repaired=True,
                    outbox_repaired=outcome.outbox_repaired,
                    inconsistency_detected=outcome.inconsistency_detected,
                )
            except ArtifactManifestConcurrencyError:
                logger.warning(
                    "artifact.reconcile.manifest_cas_failed job_id=%s artifact_kind=%s",
                    job_id,
                    artifact_kind,
                )

        if not outbox_published:
            try:
                self._outbox.mark_published(
                    job_id=job_id,
                    artifact_kind=artifact_kind,
                    destination_key=destination_key,
                    source_sha256=source_sha256,
                    size_bytes=size_bytes,
                    storage_etag=storage_etag,
                    storage_checksum_value=checksum_value,
                    storage_checksum_algorithm=checksum_algorithm,
                    verification_level=level,
                    verified_at=verified_at,
                    now=now,
                    expected_version=outbox.version,
                )
                outcome = ReconciliationOutcome(
                    manifest_repaired=outcome.manifest_repaired,
                    outbox_repaired=True,
                    inconsistency_detected=outcome.inconsistency_detected,
                )
            except ArtifactPublicationOutboxConcurrencyError:
                logger.warning(
                    "artifact.reconcile.outbox_cas_failed job_id=%s artifact_kind=%s",
                    job_id,
                    artifact_kind,
                )

        return outcome
