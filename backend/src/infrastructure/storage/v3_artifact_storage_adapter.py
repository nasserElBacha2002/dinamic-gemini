"""
Local filesystem artifact adapter.

Phase 1 keeps this adapter as legacy/local mode while adding provider-aware
operations for future S3-first flows.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from src.application.ports.services import ArtifactStorage
from src.infrastructure.storage.artifact_store import (
    ArtifactDownload,
    ArtifactStore,
    StoredArtifact,
    StoredObjectMetadata,
)


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
        sha256 = self._sha256_file(full)
        sidecar = full.with_suffix(full.suffix + ".sha256")
        sidecar.write_text(sha256, encoding="utf-8")
        return StoredArtifact(
            storage_provider="local",
            storage_bucket=None,
            storage_key=key,
            content_type=(content_type or "application/octet-stream"),
            file_size_bytes=size,
            etag=sha256,
        )

    @staticmethod
    def _sha256_file(path: Path) -> str:
        import hashlib

        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

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

    def object_size_bytes(self, key: str, *, bucket: str | None = None) -> int:
        _ = bucket  # local provider has no bucket
        full = self._resolve_safe(key)
        if not full.is_file():
            raise FileNotFoundError(f"local artifact not found: {key!r}")
        return int(full.stat().st_size)

    def read_range(
        self,
        key: str,
        *,
        start: int,
        length: int,
        bucket: str | None = None,
    ) -> bytes:
        _ = bucket  # local provider has no bucket
        if start < 0:
            raise ValueError("start must be >= 0")
        if length < 0:
            raise ValueError("length must be >= 0")
        full = self._resolve_safe(key)
        if not full.is_file():
            raise FileNotFoundError(f"local artifact not found: {key!r}")
        if length == 0:
            return b""
        with open(full, "rb") as fh:
            fh.seek(start)
            return fh.read(length)

    def download_to_path(self, key: str, target_path: Path, *, bucket: str | None = None) -> None:
        src = self._resolve_safe(key)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if src != target_path:
            shutil.copyfile(src, target_path)

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

    def get_object_metadata(self, key: str, *, bucket: str | None = None) -> StoredObjectMetadata:
        _ = bucket
        full = self._resolve_safe(key)
        if not full.is_file():
            raise FileNotFoundError(f"local artifact not found: {key!r}")
        stat = full.stat()
        size = int(stat.st_size)
        sidecar = full.with_suffix(full.suffix + ".sha256")
        sha256 = sidecar.read_text(encoding="utf-8").strip() if sidecar.is_file() else None
        return StoredObjectMetadata(
            file_size_bytes=size,
            etag=sha256,
            sha256=sha256,
            checksum_value=sha256,
            checksum_algorithm="sha256" if sha256 else None,
            updated_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
        )

    # Backward-compatible application port methods
    def save_file(self, path: str, file_obj: BinaryIO, content_type: str) -> str:
        self.put_object(path, file_obj, content_type)
        return path

    def delete_file(self, path: str) -> None:
        self.delete_object(path)
