"""Artifact storage and stored artifact reader construction (Phase C4)."""

from __future__ import annotations

import logging
from pathlib import Path

from src.application.ports.repositories import JobRepository
from src.application.ports.services import ArtifactStorage
from src.application.ports.stored_artifact_reader import StoredArtifactReader
from src.config import AppSettings

logger = logging.getLogger(__name__)


def build_artifact_storage(settings: AppSettings) -> ArtifactStorage:
    """Local or S3 artifact storage — same behavior as legacy ``AppContainer.get_artifact_storage`` body."""
    provider = (settings.artifact_storage_provider or "local").strip().lower()
    if provider == "s3":
        from src.infrastructure.storage.s3_artifact_storage_adapter import S3ArtifactStorageAdapter

        if not settings.artifact_s3_bucket:
            raise RuntimeError("ARTIFACT_S3_BUCKET is required when ARTIFACT_STORAGE_PROVIDER=s3")
        s3_storage: ArtifactStorage = S3ArtifactStorageAdapter(
            bucket=settings.artifact_s3_bucket,
            region=settings.artifact_s3_region or None,
            prefix=settings.artifact_s3_prefix,
            signed_url_ttl_sec=settings.artifact_s3_signed_url_ttl_sec,
        )
        logger.info(
            "Artifact storage configured: provider=s3 bucket=%s region=%s prefix=%s signed_url_ttl_sec=%s legacy_local_read=%s",
            settings.artifact_s3_bucket,
            settings.artifact_s3_region or "<default>",
            settings.artifact_s3_prefix,
            settings.artifact_s3_signed_url_ttl_sec,
            settings.artifact_storage_legacy_local_read_enabled,
        )
        return s3_storage

    from src.infrastructure.storage.v3_artifact_storage_adapter import V3ArtifactStorageAdapter

    base = Path(settings.output_dir) / "v3_uploads"
    base.mkdir(parents=True, exist_ok=True)
    local_storage: ArtifactStorage = V3ArtifactStorageAdapter(base)
    logger.info(
        "Artifact storage configured: provider=local base_path=%s legacy_local_read=%s",
        str(base),
        settings.artifact_storage_legacy_local_read_enabled,
    )
    return local_storage


def build_stored_artifact_reader(
    *,
    job_repo: JobRepository,
    artifact_storage: ArtifactStorage,
) -> StoredArtifactReader:
    """Hybrid reads for stored job JSON / reports."""
    from src.infrastructure.artifacts.stored_artifact_reader import DefaultStoredArtifactReader

    return DefaultStoredArtifactReader(job_repo, artifact_storage)
