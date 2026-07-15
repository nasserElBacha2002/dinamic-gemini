"""Capture staging preflight must stream (chunked hash/size), never buffer the whole file."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from src.application.dto.uploaded_file import UploadedFile
from src.application.use_cases.capture_sessions.upload_capture_session_staging_items import (
    PreflightUploadResult,
    UploadCaptureSessionStagingItemsUseCase,
)
from src.infrastructure.storage.v3_artifact_storage_adapter import V3ArtifactStorageAdapter


class _NoUnboundedReadFile:
    """Seekable fake stream that raises if ``.read()`` is called without an explicit size.

    Guards against regressions to the old "read everything into memory" preflight path
    (``hashlib`` full-buffer read + ``BytesIO(raw)``).
    """

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._pos = 0

    def read(self, size: int | None = -1) -> bytes:
        if size is None or size < 0:
            raise AssertionError("unbounded read() is not allowed during preflight")
        chunk = self._data[self._pos : self._pos + size]
        self._pos += len(chunk)
        return chunk

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self._pos = offset
        elif whence == 1:
            self._pos += offset
        elif whence == 2:
            self._pos = len(self._data) + offset
        else:
            raise ValueError(f"unsupported whence {whence}")
        return self._pos

    def tell(self) -> int:
        return self._pos


def _use_case(
    tmp_path: Path, *, max_upload_bytes: int = 1024 * 1024
) -> UploadCaptureSessionStagingItemsUseCase:
    return UploadCaptureSessionStagingItemsUseCase(
        session_repo=MagicMock(),
        item_repo=MagicMock(),
        artifact_storage=V3ArtifactStorageAdapter(tmp_path),
        clock=MagicMock(),
        staging_prefix="capture/staging",
        max_upload_bytes=max_upload_bytes,
        time_metadata_extractor=MagicMock(),
    )


def test_preflight_never_calls_unbounded_read(tmp_path: Path) -> None:
    uc = _use_case(tmp_path)
    payload = b"fake-jpeg-bytes" * 100
    fake = _NoUnboundedReadFile(payload)
    uf = UploadedFile("photo.jpg", fake, "image/jpeg")

    result, err = uc._preflight_one_upload_file(
        uf, "photo.jpg", 0, session_hashes=set(), batch_digests=set()
    )

    assert err is None
    assert isinstance(result, PreflightUploadResult)
    assert result.size_bytes == len(payload)
    # Position restored to 0 so the caller can hand file_obj straight to storage.
    assert fake.tell() == 0


def test_preflight_rejects_zero_byte_file_without_unbounded_read(tmp_path: Path) -> None:
    uc = _use_case(tmp_path)
    fake = _NoUnboundedReadFile(b"")
    uf = UploadedFile("empty.jpg", fake, "image/jpeg")

    result, err = uc._preflight_one_upload_file(
        uf, "empty.jpg", 0, session_hashes=set(), batch_digests=set()
    )

    assert result is None
    assert err is not None
    assert err.code == "ZERO_BYTE_FILE"


def test_preflight_rejects_too_large_file_without_unbounded_read(tmp_path: Path) -> None:
    uc = _use_case(tmp_path, max_upload_bytes=10)
    fake = _NoUnboundedReadFile(b"x" * 4096)
    uf = UploadedFile("big.jpg", fake, "image/jpeg")

    result, err = uc._preflight_one_upload_file(
        uf, "big.jpg", 0, session_hashes=set(), batch_digests=set()
    )

    assert result is None
    assert err is not None
    assert err.code == "CAPTURE_SESSION_STAGING_FILE_TOO_LARGE"


def test_preflight_detects_duplicate_content_within_batch_without_unbounded_read(
    tmp_path: Path,
) -> None:
    uc = _use_case(tmp_path)
    payload = b"same-bytes"
    first = _NoUnboundedReadFile(payload)
    second = _NoUnboundedReadFile(payload)
    uf1 = UploadedFile("a.jpg", first, "image/jpeg")
    uf2 = UploadedFile("b.jpg", second, "image/jpeg")
    batch_digests: set[str] = set()

    result1, err1 = uc._preflight_one_upload_file(
        uf1, "a.jpg", 0, session_hashes=set(), batch_digests=batch_digests
    )
    assert err1 is None
    assert result1 is not None
    batch_digests.add(result1.digest)

    result2, err2 = uc._preflight_one_upload_file(
        uf2, "b.jpg", 1, session_hashes=set(), batch_digests=batch_digests
    )
    assert result2 is None
    assert err2 is not None
    assert err2.code == "CAPTURE_SESSION_DUPLICATE_ITEM_CONTENT"
