"""
Local filesystem artifact adapter.

Phase 1 keeps this adapter as legacy/local mode while adding provider-aware
operations for future S3-first flows.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import BinaryIO

from src.application.ports.services import ArtifactStorage
from src.infrastructure.storage.artifact_store import ArtifactDownload, ArtifactStore, StoredArtifact


class V3ArtifactStorageAdapter(ArtifactStorage, ArtifactStore):
    """Local provider-backed artifact storage rooted at base_path."""

    def __init__(self, base_path: Path) -> None:
        self._base = Path(base_path).resolve()

    def _resolve_safe(self, key: str) -> Path:
        full = (self._base / key).resolve()
        try:
            full.relative_to(self._base)
        except ValueError as exc:
            raise ValueError("Path must not escape base directory") from exc
        return full

    def put_object(self, key: str, file_obj: BinaryIO, content_type: str) -> StoredArtifact:
        full = self._resolve_safe(key)
        full.parent.mkdir(parents=True, exist_ok=True)
        with open(full, "wb") as dest:
            shutil.copyfileobj(file_obj, dest)
        size = int(full.stat().st_size)
        return StoredArtifact(
            storage_provider="local",
            storage_bucket=None,
            storage_key=key,
            content_type=(content_type or "application/octet-stream"),
            file_size_bytes=size,
            etag=None,
        )

    def get_object(self, key: str) -> ArtifactDownload:
        full = self._resolve_safe(key)
        with open(full, "rb") as src:
            data = src.read()
        return ArtifactDownload(
            content=data,
            content_type="application/octet-stream",
            file_size_bytes=len(data),
            etag=None,
        )

    def delete_object(self, key: str) -> None:
        full = self._resolve_safe(key)
        try:
            full.unlink(missing_ok=True)
        except TypeError:
            if full.exists():
                full.unlink()

    def object_exists(self, key: str) -> bool:
        full = self._resolve_safe(key)
        return full.exists() and full.is_file()

    def generate_signed_url(self, key: str, expires_in_sec: int) -> str:
        raise NotImplementedError("Signed URL is not supported for local storage provider")

    # Backward-compatible application port methods
    def save_file(self, path: str, file_obj: BinaryIO, content_type: str) -> str:
        self.put_object(path, file_obj, content_type)
        return path

    def delete_file(self, path: str) -> None:
        self.delete_object(path)
