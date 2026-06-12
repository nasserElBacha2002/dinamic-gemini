"""Finalization-specific exceptions for worker artifact publication — Phase 3.2."""

from __future__ import annotations

from typing import Any


class ArtifactStoreUnavailableError(RuntimeError):
    """Raised when durable artifact storage is not configured or unreachable."""


class ArtifactPublishError(RuntimeError):
    """Raised when a required durable artifact cannot be uploaded (no prior success in batch)."""


class ArtifactPublishPartialError(ArtifactPublishError):
    """Raised when some required artifacts uploaded but a later required upload failed."""

    def __init__(
        self,
        message: str,
        *,
        published: dict[str, dict[str, Any]],
        failed_kind: str,
    ) -> None:
        super().__init__(message)
        self.published = published
        self.failed_kind = failed_kind
