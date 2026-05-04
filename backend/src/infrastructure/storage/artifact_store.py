"""
Provider-aware artifact storage abstraction (Phase 1 S3 foundation; Phase 6 contract).

This abstraction is intentionally infrastructure-facing and can be implemented by
S3, local filesystem, or composite adapters during migration.

**storage_key (canonical)**

- Persisted in the DB and passed to ArtifactStore methods as the **logical** application key
  relative to the configured **S3 bucket key prefix** (from env, e.g. ``v3``): that prefix
  string must **not** be duplicated in ``storage_key`` (use ``jobs/{id}/run/log.jsonl``, not
  ``v3/jobs/...``). Application path segments such as ``jobs/`` or ``uploads/`` are not the
  same as the bucket prefix.
- S3: adapters prepend the bucket prefix to logical keys, and tolerate caller keys that
  already include that prefix (no double prefix). Return values from ``put_object`` /
  ``StoredArtifact.storage_key`` use the same logical form the caller passed (bucket prefix
  stripped only from values returned after an upload keyed with the full physical path—see
  S3 adapter).
- Local (``V3ArtifactStorageAdapter``): ``storage_key`` is the path relative to the adapter
  base (typically the same relative layout as ``storage_path`` for uploads).

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
from typing import BinaryIO


@dataclass(frozen=True)
class StoredArtifact:
    """Canonical metadata returned after writing an artifact.

    Contract: ``storage_key`` is the logical application key (no duplication of the
    configured S3 bucket prefix). Suitable for DB persistence and ArtifactStore calls.
    """

    storage_provider: str
    storage_bucket: str | None
    storage_key: str
    content_type: str
    file_size_bytes: int
    etag: str | None = None


@dataclass(frozen=True)
class ArtifactDownload:
    """Canonical bytes payload returned by storage reads."""

    content: bytes
    content_type: str
    file_size_bytes: int
    etag: str | None = None


class ArtifactStore(ABC):
    """Storage provider contract for durable artifacts."""

    @abstractmethod
    def put_object(self, key: str, file_obj: BinaryIO, content_type: str) -> StoredArtifact: ...

    @abstractmethod
    def get_object(self, key: str) -> ArtifactDownload: ...

    @abstractmethod
    def object_size_bytes(self, key: str, *, bucket: str | None = None) -> int:
        """Return object size without reading the body (e.g. S3 head or local stat)."""

    @abstractmethod
    def download_to_path(
        self, key: str, target_path: Path, *, bucket: str | None = None
    ) -> None:
        """Download object directly to local path without buffering full content in memory."""
        ...

    @abstractmethod
    def delete_object(self, key: str) -> None: ...

    @abstractmethod
    def object_exists(self, key: str) -> bool: ...

    @abstractmethod
    def generate_signed_url(self, key: str, expires_in_sec: int) -> str: ...
