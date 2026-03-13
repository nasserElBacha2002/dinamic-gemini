"""
V3 ArtifactStorage adapter — implements application port for aisle asset uploads.

Writes files under a configurable base path (e.g. output_dir/v3_uploads).
Returns the path used (relative to base) as string for persistence.
Uses streaming copy to avoid loading large files (e.g. videos) fully into memory.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import BinaryIO

from src.application.ports.services import ArtifactStorage


class V3ArtifactStorageAdapter(ArtifactStorage):
    """
    Saves uploaded files under base_path. save_file(path, file_obj, content_type)
    writes to base_path / path and returns path as string (relative).
    Rejects path traversal (path must not resolve outside base).
    Uses chunked copy (shutil.copyfileobj) so large files are not fully loaded into memory.
    """

    def __init__(self, base_path: Path) -> None:
        self._base = Path(base_path).resolve()

    def save_file(self, path: str, file_obj: BinaryIO, content_type: str) -> str:
        full = (self._base / path).resolve()
        try:
            full.relative_to(self._base)
        except ValueError:
            raise ValueError("Path must not escape base directory")
        full.parent.mkdir(parents=True, exist_ok=True)
        with open(full, "wb") as dest:
            shutil.copyfileobj(file_obj, dest)
        return path
