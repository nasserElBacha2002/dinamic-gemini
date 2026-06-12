"""Object verification for artifact publication — Phase 3.5 corrections."""

from __future__ import annotations

from src.domain.jobs.artifact_publication_outbox import ArtifactVerificationLevel
from src.infrastructure.storage.artifact_store import ArtifactStore, StoredObjectMetadata


def verify_remote_object(
    *,
    artifact_store: ArtifactStore,
    destination_key: str,
    expected_sha256: str,
    expected_size: int | None,
) -> tuple[ArtifactVerificationLevel, StoredObjectMetadata | None]:
    if not artifact_store.object_exists(destination_key):
        return ArtifactVerificationLevel.UNVERIFIABLE, None
    metadata = artifact_store.get_object_metadata(destination_key)
    if metadata.sha256 and metadata.sha256 == expected_sha256:
        return ArtifactVerificationLevel.CONFIRMED, metadata
    if (
        metadata.checksum_algorithm
        and metadata.checksum_algorithm.lower() in {"sha256", "sha-256"}
        and metadata.checksum_value
        and metadata.checksum_value == expected_sha256
    ):
        return ArtifactVerificationLevel.CONFIRMED, metadata
    if expected_size is not None and metadata.file_size_bytes == expected_size:
        return ArtifactVerificationLevel.POSITIVE_EVIDENCE_ONLY, metadata
    return ArtifactVerificationLevel.UNVERIFIABLE, metadata
