"""Snapshot aisle source assets onto a job attempt for Observability."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import uuid4

from src.application.ports.job_source_asset_repository import (
    JobSourceAssetLink,
    JobSourceAssetRepository,
)
from src.domain.assets.entities import SourceAsset, SourceAssetType


def build_job_source_asset_links(
    *,
    job_id: str,
    assets: Sequence[SourceAsset],
    stage: str = "SOURCE_ASSETS_RESOLVED",
    now: datetime | None = None,
) -> list[JobSourceAssetLink]:
    created = now or datetime.now(timezone.utc)
    links: list[JobSourceAssetLink] = []
    for index, asset in enumerate(assets):
        role = "video" if asset.type == SourceAssetType.VIDEO else "primary"
        links.append(
            JobSourceAssetLink(
                id=str(uuid4()),
                job_id=job_id,
                source_asset_id=str(asset.id),
                asset_role=role,
                position_order=index,
                checksum=None,
                storage_key=(asset.storage_key or asset.storage_path or None),
                mime_type=asset.mime_type or asset.content_type,
                size_bytes=asset.file_size_bytes,
                width=None,
                height=None,
                stage=stage,
                provider_request_id=None,
                created_at=created,
            )
        )
    return links


def persist_job_source_asset_snapshot(
    repo: JobSourceAssetRepository | None,
    *,
    job_id: str,
    assets: Sequence[SourceAsset],
    stage: str = "SOURCE_ASSETS_RESOLVED",
) -> list[JobSourceAssetLink]:
    links = build_job_source_asset_links(job_id=job_id, assets=assets, stage=stage)
    if repo is not None:
        repo.replace_for_job(job_id, links)
    return links
