"""Streaming helpers for upload ingest (chunked hash / size without full buffering)."""

from __future__ import annotations

import hashlib
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import BinaryIO

from src.application.dto.uploaded_file import UploadedFile

_DEFAULT_CHUNK = 1024 * 1024


def spool_upload_to_tempfile(
    source: BinaryIO,
    *,
    max_file_bytes: int,
    chunk_size: int = _DEFAULT_CHUNK,
) -> tuple[tempfile.SpooledTemporaryFile[bytes], int, str]:
    """Copy ``source`` into a spooled temp file, enforce max size, return (file, size, sha256).

    The returned file is seeked to 0. Caller owns closing it.
    """
    hasher = hashlib.sha256()
    dest: tempfile.SpooledTemporaryFile[bytes] = tempfile.SpooledTemporaryFile(
        max_size=min(8 * 1024 * 1024, max_file_bytes),
        mode="w+b",
    )
    total = 0
    while True:
        chunk = source.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_file_bytes:
            dest.close()
            raise ValueError(f"file exceeds max size ({max_file_bytes})")
        hasher.update(chunk)
        dest.write(chunk)
    dest.seek(0)
    return dest, total, hasher.hexdigest()


def sha256_fileobj(file_obj: BinaryIO, *, chunk_size: int = _DEFAULT_CHUNK) -> str:
    """Compute SHA-256 of a seekable file-like object; restores original position."""
    pos = file_obj.tell()
    try:
        file_obj.seek(0)
        hasher = hashlib.sha256()
        while True:
            chunk = file_obj.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
        return hasher.hexdigest()
    finally:
        file_obj.seek(pos)


def measure_fileobj_size(file_obj: BinaryIO) -> int:
    pos = file_obj.tell()
    try:
        file_obj.seek(0, 2)
        end = file_obj.tell()
        return int(end) if isinstance(end, int) else 0
    finally:
        file_obj.seek(pos)


def close_quietly(file_obj: object) -> None:
    closer = getattr(file_obj, "close", None)
    if callable(closer):
        try:
            closer()
        except Exception:
            pass


def close_uploaded_files(files: Sequence[UploadedFile]) -> None:
    """Best-effort close of every ``file_obj`` in ``files`` (route-level cleanup, always run)."""
    for uf in files:
        close_quietly(uf.file_obj)


def unlink_quietly(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except TypeError:
        if path.exists():
            try:
                path.unlink()
            except Exception:
                pass
    except Exception:
        pass
