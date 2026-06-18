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


def resolve_publication_verification_level(
    *,
    level: ArtifactVerificationLevel,
    metadata: StoredObjectMetadata | None,
    expected_sha256: str,
    expected_size: int | None,
    trust_size_matched_upload: bool,
) -> ArtifactVerificationLevel:
    """
    Upgrade size-only remote evidence to CONFIRMED when the expected SHA-256 was known
  before upload and the remote object size matches.

    Cloud object stores (S3/GCS) often expose size but not SHA-256 in HEAD metadata.
    """
    if level == ArtifactVerificationLevel.CONFIRMED:
        return level
    if not trust_size_matched_upload or not expected_sha256:
        return level
    if level != ArtifactVerificationLevel.POSITIVE_EVIDENCE_ONLY or metadata is None:
        return level
    if expected_size is None or metadata.file_size_bytes != expected_size:
        return level
    return ArtifactVerificationLevel.CONFIRMED
