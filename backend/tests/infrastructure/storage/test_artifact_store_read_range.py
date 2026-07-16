"""Tests for ``ArtifactStore.read_range`` default fallback and the local adapter override."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import pytest

from src.infrastructure.storage.artifact_store import (
    ArtifactDownload,
    ArtifactStore,
    StoredArtifact,
)
from src.infrastructure.storage.v3_artifact_storage_adapter import V3ArtifactStorageAdapter


class _MinimalArtifactStore(ArtifactStore):
    """Exercises only the base class's default ``read_range`` fallback (no override)."""

    def __init__(self, content: bytes) -> None:
        self._content = content

    def put_object(self, key: str, file_obj: BinaryIO, content_type: str) -> StoredArtifact:
        raise NotImplementedError

    def get_object(self, key: str) -> ArtifactDownload:
        return ArtifactDownload(
            content=self._content,
            content_type="application/octet-stream",
            file_size_bytes=len(self._content),
        )

    def object_size_bytes(self, key: str, *, bucket: str | None = None) -> int:
        return len(self._content)

    def download_to_path(self, key: str, target_path: Path, *, bucket: str | None = None) -> None:
        raise NotImplementedError

    def delete_object(self, key: str) -> None:
        raise NotImplementedError

    def object_exists(self, key: str) -> bool:
        return True

    def generate_signed_url(self, key: str, expires_in_sec: int) -> str:
        raise NotImplementedError


def test_default_read_range_fallback_slices_full_object() -> None:
    store = _MinimalArtifactStore(b"0123456789")

    assert store.read_range("any-key", start=2, length=4) == b"2345"
    # Reading past EOF returns whatever remains rather than raising.
    assert store.read_range("any-key", start=8, length=10) == b"89"
    assert store.read_range("any-key", start=0, length=0) == b""


def test_default_read_range_rejects_negative_start_or_length() -> None:
    store = _MinimalArtifactStore(b"abcd")
    with pytest.raises(ValueError, match="start"):
        store.read_range("any-key", start=-1, length=1)
    with pytest.raises(ValueError, match="length"):
        store.read_range("any-key", start=0, length=-1)


def test_local_adapter_read_range_seeks_and_reads_without_loading_whole_file(
    tmp_path: Path,
) -> None:
    adapter = V3ArtifactStorageAdapter(base_path=tmp_path)
    adapter.put_object("uploads/x.bin", BytesIO(b"0123456789"), "application/octet-stream")

    assert adapter.read_range("uploads/x.bin", start=2, length=4) == b"2345"
    assert adapter.read_range("uploads/x.bin", start=8, length=10) == b"89"
    assert adapter.read_range("uploads/x.bin", start=0, length=0) == b""


def test_local_adapter_read_range_missing_file_raises() -> None:
    adapter = V3ArtifactStorageAdapter(base_path=Path("/tmp"))
    with pytest.raises(FileNotFoundError):
        adapter.read_range("does/not/exist.bin", start=0, length=1)


def test_local_adapter_get_object_metadata_includes_updated_at(tmp_path: Path) -> None:
    adapter = V3ArtifactStorageAdapter(base_path=tmp_path)
    adapter.put_object("uploads/meta.bin", BytesIO(b"hello"), "application/octet-stream")

    meta = adapter.get_object_metadata("uploads/meta.bin")
    assert meta.file_size_bytes == 5
    assert meta.sha256 is not None
    assert meta.updated_at is not None
