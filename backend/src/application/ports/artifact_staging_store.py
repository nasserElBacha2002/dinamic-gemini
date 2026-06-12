"""Durable artifact source staging — Phase 3.5 corrections."""

from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO, Protocol, runtime_checkable


@dataclass(frozen=True)
class StagedArtifactSource:
    staging_key: str
    source_sha256: str
    size_bytes: int


@runtime_checkable
class ArtifactStagingStore(Protocol):
    def put_exact_source(
        self,
        *,
        job_id: str,
        artifact_kind: str,
        file_obj: BinaryIO,
    ) -> StagedArtifactSource: ...

    def open_source(self, staging_key: str) -> BinaryIO: ...

    def source_exists(self, staging_key: str) -> bool: ...

    def source_size(self, staging_key: str) -> int: ...

    def source_checksum(self, staging_key: str) -> str: ...

    def delete_source(self, staging_key: str) -> None: ...
