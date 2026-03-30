"""
Provider-aware artifact storage abstraction (Phase 1 S3 foundation).

This abstraction is intentionally infrastructure-facing and can be implemented by
S3, local filesystem, or composite adapters during migration.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import BinaryIO, Optional


@dataclass(frozen=True)
class StoredArtifact:
    """Canonical metadata returned after writing an artifact."""

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
    def delete_object(self, key: str) -> None:
        ...

    @abstractmethod
    def object_exists(self, key: str) -> bool:
        ...

    @abstractmethod
    def generate_signed_url(self, key: str, expires_in_sec: int) -> str:
        ...
