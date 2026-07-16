"""Persisted association between a job attempt and the source assets it used."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class JobSourceAssetLink:
    id: str
    job_id: str
    source_asset_id: str
    asset_role: str  # primary | reference | video | frame
    position_order: int
    checksum: str | None
    storage_key: str | None
    mime_type: str | None
    size_bytes: int | None
    width: int | None
    height: int | None
    stage: str | None
    provider_request_id: str | None
    created_at: datetime
    #: Display name for Observability catalog views; preferred over storage_key basename.
    original_filename: str | None = None
    #: Derived-asset lineage (e.g. "resize", "crop") when this link is not the raw upload.
    transformation: str | None = None
    #: Historical reference to the source_assets row this link was derived from (no FK — Option B).
    source_parent_id: str | None = None
    #: Correlates this link to a generated/observability artifact id, when applicable.
    artifact_id: str | None = None
    #: Monotonic version for immutable, append-only snapshots of the same job attempt.
    snapshot_version: int = 1


class JobSourceAssetRepository(Protocol):
    def replace_for_job(self, job_id: str, links: Sequence[JobSourceAssetLink]) -> None:
        """Replace the snapshot for a job attempt.

        Pragmatic immutability guard: once any existing link for ``job_id`` carries a non-null
        ``provider_request_id`` (i.e. the provider call has started), the snapshot is considered
        immutable and callers must raise ``ValueError("SNAPSHOT_IMMUTABLE")`` instead of deleting
        rows. Pre-provider snapshots (``provider_request_id IS NULL``) may still be replaced.
        """
        ...

    def list_for_job(self, job_id: str) -> list[JobSourceAssetLink]: ...
