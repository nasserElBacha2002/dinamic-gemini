"""Filesystem durable artifact staging — Phase 3.5 corrections."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import BinaryIO

from src.application.ports.artifact_staging_store import ArtifactStagingStore, StagedArtifactSource


class FileSystemArtifactStagingStore(ArtifactStagingStore):
    def __init__(self, base_path: Path | str) -> None:
        self._base = Path(base_path).resolve()
        self._base.mkdir(parents=True, exist_ok=True)

    def _resolve(self, staging_key: str) -> Path:
        full = (self._base / staging_key).resolve()
        if not str(full).startswith(str(self._base)):
            raise ValueError("staging key escapes base path")
        return full

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def put_exact_source(
        self,
        *,
        job_id: str,
        artifact_kind: str,
        file_obj: BinaryIO,
    ) -> StagedArtifactSource:
        temp_path = self._base / ".tmp" / job_id / artifact_kind
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_path, "wb") as dest:
            shutil.copyfileobj(file_obj, dest)
        source_sha256 = self._sha256_file(temp_path)
        size_bytes = temp_path.stat().st_size
        staging_key = f"artifact-staging/{job_id}/{artifact_kind}/{source_sha256}"
        final_path = self._resolve(staging_key)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        if not final_path.exists():
            temp_path.replace(final_path)
        else:
            temp_path.unlink(missing_ok=True)
        return StagedArtifactSource(
            staging_key=staging_key,
            source_sha256=source_sha256,
            size_bytes=size_bytes,
        )

    def open_source(self, staging_key: str) -> BinaryIO:
        return open(self._resolve(staging_key), "rb")

    def source_exists(self, staging_key: str) -> bool:
        path = self._resolve(staging_key)
        return path.is_file()

    def source_size(self, staging_key: str) -> int:
        return int(self._resolve(staging_key).stat().st_size)

    def source_checksum(self, staging_key: str) -> str:
        return self._sha256_file(self._resolve(staging_key))

    def delete_source(self, staging_key: str) -> None:
        path = self._resolve(staging_key)
        if path.is_file():
            path.unlink()
