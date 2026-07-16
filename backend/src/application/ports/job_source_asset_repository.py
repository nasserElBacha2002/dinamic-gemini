"""Persisted association between a job attempt and the source assets it used."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Sequence


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


class JobSourceAssetRepository(Protocol):
    def replace_for_job(self, job_id: str, links: Sequence[JobSourceAssetLink]) -> None: ...

    def list_for_job(self, job_id: str) -> list[JobSourceAssetLink]: ...
