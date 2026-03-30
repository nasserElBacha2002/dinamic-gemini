"""
Provider-aware artifact storage abstraction (Phase 1 S3 foundation; Phase 6 contract).

This abstraction is intentionally infrastructure-facing and can be implemented by
S3, local filesystem, or composite adapters during migration.

**storage_key (canonical)**

- Persisted in the DB and passed to ArtifactStore methods as the **logical** application key:
  **prefix-free** relative to any provider-specific root (e.g. S3 prefix is *not* part of
  the stored value).
- S3: adapters accept **logical** keys and also tolerate keys that already include the
  configured bucket prefix (idempotent normalization — no double prefix). Return values from
  ``put_object`` / ``StoredArtifact.storage_key`` are always **logical** (prefix stripped).
- Local (``V3ArtifactStorageAdapter``): ``storage_key`` is the path relative to
  ``v3_uploads`` / ``base_path`` (same string historically kept in ``storage_path`` for uploads).

**content_type vs domain mime_type**

- ``StoredArtifact.content_type`` / DB ``content_type`` = object storage metadata (HTTP Content-Type).
- Domain/API fields named ``mime_type`` describe the asset for business rules and responses.
  Populate both on upload when they align; conversions belong at boundaries, not inside adapters.

**storage_path (legacy)**

- Legacy-only relative filesystem path for rows without provider metadata. Do not use it to
  infer ``storage_key`` when ``storage_provider`` is set (see ``sql_storage_fields``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Optional


@dataclass(frozen=True)
class StoredArtifact:
    """Canonical metadata returned after writing an artifact.

    Contract: ``storage_key`` is the logical application key (prefix-free), suitable
    for DB persistence and passing back to ArtifactStore operations. Provider adapters
    are responsible for mapping this logical key to physical object identifiers.
    """

    storage_provider: str
    storage_bucket: Optional[str]
    storage_key: str
    content_type: str
    file_size_bytes: int
    etag: Optional[str] = None


@dataclass(frozen=True)
class ArtifactDownload:
    """Canonical bytes payload returned by storage reads."""

    content: bytes
    content_type: str
    file_size_bytes: int
    etag: Optional[str] = None


class ArtifactStore(ABC):
    """Storage provider contract for durable artifacts."""

    @abstractmethod
    def put_object(self, key: str, file_obj: BinaryIO, content_type: str) -> StoredArtifact:
        ...

    @abstractmethod
    def get_object(self, key: str) -> ArtifactDownload:
        ...

    @abstractmethod
    def object_size_bytes(self, key: str, *, bucket: Optional[str] = None) -> int:
        """Return object size without reading the body (e.g. S3 head or local stat)."""

    @abstractmethod
    def download_to_path(self, key: str, target_path: Path, *, bucket: Optional[str] = None) -> None:
        """Download object directly to local path without buffering full content in memory."""
        ...

    @abstractmethod
    def delete_object(self, key: str) -> None:
        ...

    @abstractmethod
    def object_exists(self, key: str) -> bool:
        ...

    @abstractmethod
    def generate_signed_url(self, key: str, expires_in_sec: int) -> str:
        ...
