"""Snapshot aisle source assets onto a job attempt for Observability."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid5

from src.application.errors import InputSnapshotPersistError
from src.application.ports.job_source_asset_repository import (
    JobSourceAssetLink,
    JobSourceAssetRepository,
)
from src.domain.assets.entities import SourceAsset, SourceAssetType

__all__ = [
    "InputSnapshotPersistError",
    "SnapshotPersistResult",
    "build_job_source_asset_links",
    "persist_job_source_asset_snapshot",
    "persist_job_source_asset_snapshot_checked",
]

#: Stable namespace for deterministic job-source-asset link ids (uuid5). Keeping this fixed makes
#: re-snapshotting the same (job, asset, role, position, provider_request) idempotent.
_LINK_ID_NAMESPACE = UUID("2f6c8e3a-7b1d-4a9c-9e2f-5d8a1c4b6f70")


@dataclass(frozen=True)
class SnapshotPersistResult:
    """Outcome of a best-effort (non-required) snapshot persist attempt."""

    ok: bool
    links: list[JobSourceAssetLink] = field(default_factory=list)
    warning: str | None = None


def _is_reference_asset(asset: SourceAsset) -> bool:
    """Best-effort reference-role detection.

    ``SourceAssetType`` currently only enumerates ``photo``/``video``; this stays forward
    compatible with a future ``reference`` type or a ``metadata_json`` role hint without
    requiring a schema/enum change today.
    """
    type_value = getattr(asset.type, "value", asset.type)
    if str(type_value).strip().lower() == "reference":
        return True
    metadata = asset.metadata_json or {}
    return str(metadata.get("role", "")).strip().lower() == "reference"


def _deterministic_link_id(
    *,
    job_id: str,
    source_asset_id: str,
    role: str,
    position: int,
    provider_request_id: str | None,
) -> str:
    key = f"{job_id}|{source_asset_id}|{role}|{position}|{provider_request_id or ''}"
    return str(uuid5(_LINK_ID_NAMESPACE, key))


def build_job_source_asset_links(
    *,
    job_id: str,
    assets: Sequence[SourceAsset],
    stage: str = "SOURCE_ASSETS_RESOLVED",
    now: datetime | None = None,
    provider_request_id: str | None = None,
) -> list[JobSourceAssetLink]:
    created = now or datetime.now(timezone.utc)
    links: list[JobSourceAssetLink] = []
    for index, asset in enumerate(assets):
        if asset.type == SourceAssetType.VIDEO:
            role = "video"
        elif _is_reference_asset(asset):
            role = "reference"
        else:
            role = "primary"
        links.append(
            JobSourceAssetLink(
                id=_deterministic_link_id(
                    job_id=job_id,
                    source_asset_id=str(asset.id),
                    role=role,
                    position=index,
                    provider_request_id=provider_request_id,
                ),
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
                provider_request_id=provider_request_id,
                created_at=created,
                original_filename=asset.original_filename or None,
            )
        )
    return links


def persist_job_source_asset_snapshot(
    repo: JobSourceAssetRepository | None,
    *,
    job_id: str,
    assets: Sequence[SourceAsset],
    stage: str = "SOURCE_ASSETS_RESOLVED",
    provider_request_id: str | None = None,
) -> list[JobSourceAssetLink]:
    """Best-effort snapshot persist — kept for backward compatibility.

    Raises whatever the repository raises (including ``ValueError("SNAPSHOT_IMMUTABLE")``).
    Prefer :func:`persist_job_source_asset_snapshot_checked` for callers that need to honor
    ``OBSERVABILITY_INPUT_SNAPSHOT_REQUIRED``.
    """
    links = build_job_source_asset_links(
        job_id=job_id, assets=assets, stage=stage, provider_request_id=provider_request_id
    )
    if repo is not None:
        repo.replace_for_job(job_id, links)
    return links


def persist_job_source_asset_snapshot_checked(
    repo: JobSourceAssetRepository | None,
    *,
    job_id: str,
    assets: Sequence[SourceAsset],
    stage: str = "SOURCE_ASSETS_RESOLVED",
    provider_request_id: str | None = None,
    required: bool | None = None,
) -> SnapshotPersistResult:
    """Persist the job input snapshot, honoring ``OBSERVABILITY_INPUT_SNAPSHOT_REQUIRED``.

    - ``required`` (or the setting, when ``None``) True: on failure raises
      :class:`InputSnapshotPersistError` so the caller can fail the job deterministically.
    - ``required`` False: on failure returns ``SnapshotPersistResult(ok=False, warning=...)``
      instead of silently swallowing the error, so callers can flag the job result without
      aborting the run.
    """
    if required is None:
        from src.config import load_settings

        required = bool(load_settings().observability_input_snapshot_required)

    links = build_job_source_asset_links(
        job_id=job_id, assets=assets, stage=stage, provider_request_id=provider_request_id
    )
    if repo is None:
        return SnapshotPersistResult(ok=True, links=links, warning=None)
    try:
        repo.replace_for_job(job_id, links)
    except Exception as exc:
        message = f"job_source_asset_snapshot_failed job_id={job_id}: {exc}"
        if required:
            raise InputSnapshotPersistError(message, cause=exc) from exc
        return SnapshotPersistResult(ok=False, links=[], warning=message)
    return SnapshotPersistResult(ok=True, links=links, warning=None)
