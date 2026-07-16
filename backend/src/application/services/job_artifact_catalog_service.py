"""Unified read model for Observability job artifacts (manifest + aisle source assets)."""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid5

from src.application.ports.artifact_manifest_store import ArtifactManifestStore
from src.application.ports.repositories import SourceAssetRepository
from src.domain.assets.entities import SourceAssetType
from src.domain.jobs.artifact_manifest import ArtifactManifestEntry, ArtifactManifestStatus
from src.domain.jobs.artifact_policy import (
    ARTIFACT_KIND_EXECUTION_LOG,
    ARTIFACT_KIND_HYBRID_REPORT_CSV,
    ARTIFACT_KIND_HYBRID_REPORT_JSON,
    ARTIFACT_KIND_TRACEABILITY_MANIFEST,
)
from src.domain.jobs.entities import Job


class ArtifactCategory(str, Enum):
    INPUT = "INPUT"
    INTERMEDIATE = "INTERMEDIATE"
    OUTPUT = "OUTPUT"
    LOG = "LOG"
    DEBUG = "DEBUG"
    EXPORT = "EXPORT"


class ArtifactAvailabilityStatus(str, Enum):
    PENDING = "PENDING"
    AVAILABLE = "AVAILABLE"
    PUBLISH_FAILED = "PUBLISH_FAILED"
    MISSING = "MISSING"
    EXPIRED = "EXPIRED"
    DELETED = "DELETED"
    CORRUPTED = "CORRUPTED"


_KIND_CATEGORY: dict[str, ArtifactCategory] = {
    ARTIFACT_KIND_EXECUTION_LOG: ArtifactCategory.LOG,
    ARTIFACT_KIND_HYBRID_REPORT_JSON: ArtifactCategory.OUTPUT,
    ARTIFACT_KIND_HYBRID_REPORT_CSV: ArtifactCategory.EXPORT,
    ARTIFACT_KIND_TRACEABILITY_MANIFEST: ArtifactCategory.OUTPUT,
    "source_image": ArtifactCategory.INPUT,
    "source_video": ArtifactCategory.INPUT,
    "reference_image": ArtifactCategory.INPUT,
}

_KIND_MIME: dict[str, str] = {
    ARTIFACT_KIND_EXECUTION_LOG: "application/x-ndjson",
    ARTIFACT_KIND_HYBRID_REPORT_JSON: "application/json",
    ARTIFACT_KIND_HYBRID_REPORT_CSV: "text/csv",
    ARTIFACT_KIND_TRACEABILITY_MANIFEST: "application/json",
}

# Stable namespace for synthetic artifact ids derived from (job_id, kind) or source assets.
_ARTIFACT_NS = UUID("a7e2c4b1-9f33-4d8e-8c1a-0b6f5e4d3c2a")


@dataclass(frozen=True)
class JobArtifactView:
    id: str
    job_id: str
    category: ArtifactCategory
    kind: str
    stage: str | None
    display_name: str
    original_filename: str | None
    mime_type: str | None
    size_bytes: int | None
    checksum: str | None
    width: int | None
    height: int | None
    status: ArtifactAvailabilityStatus
    is_current: bool
    is_previewable: bool
    is_downloadable: bool
    created_at: datetime | None
    published_at: datetime | None
    expires_at: datetime | None
    source_type: str
    source_asset_id: str | None
    # Internal only — never serialize to API responses.
    storage_key: str | None = None


@dataclass(frozen=True)
class JobArtifactPage:
    items: list[JobArtifactView]
    next_cursor: str | None
    has_more: bool


def _manifest_status(entry: ArtifactManifestEntry) -> ArtifactAvailabilityStatus:
    if entry.status == ArtifactManifestStatus.PUBLISHED:
        if not (entry.storage_key or "").strip():
            return ArtifactAvailabilityStatus.MISSING
        return ArtifactAvailabilityStatus.AVAILABLE
    if entry.status == ArtifactManifestStatus.FAILED:
        return ArtifactAvailabilityStatus.PUBLISH_FAILED
    if entry.status == ArtifactManifestStatus.PENDING:
        return ArtifactAvailabilityStatus.PENDING
    return ArtifactAvailabilityStatus.MISSING


def _artifact_id(*, job_id: str, kind: str, source_asset_id: str | None = None) -> str:
    seed = f"{job_id}:{kind}:{source_asset_id or ''}"
    return str(uuid5(_ARTIFACT_NS, seed))


def encode_artifact_cursor(offset: int) -> str:
    raw = f"o:{offset}".encode()
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_artifact_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        pad = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(cursor + pad).decode("utf-8")
        if raw.startswith("o:"):
            return max(0, int(raw[2:]))
    except Exception:
        return 0
    return 0


class JobArtifactCatalogService:
    """Assemble Observability artifact catalog for one job without exposing storage keys."""

    def __init__(
        self,
        *,
        manifest_store: ArtifactManifestStore | None,
        source_asset_repo: SourceAssetRepository | None,
    ) -> None:
        self._manifest = manifest_store
        self._assets = source_asset_repo

    def list_for_job(
        self,
        job: Job,
        *,
        aisle_id: str,
        category: str | None = None,
        kind: str | None = None,
        status: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
        is_current: bool | None = None,
    ) -> JobArtifactPage:
        items = self._collect(job, aisle_id=aisle_id)
        if category:
            cat = category.strip().upper()
            items = [i for i in items if i.category.value == cat]
        if kind:
            k = kind.strip()
            items = [i for i in items if i.kind == k]
        if status:
            st = status.strip().upper()
            items = [i for i in items if i.status.value == st]
        if is_current is not None:
            items = [i for i in items if i.is_current is is_current]

        items.sort(key=lambda a: (a.category.value, a.kind, a.id))
        offset = decode_artifact_cursor(cursor)
        limit = max(1, min(int(limit), 200))
        window = items[offset : offset + limit]
        next_off = offset + len(window)
        has_more = next_off < len(items)
        return JobArtifactPage(
            items=window,
            next_cursor=encode_artifact_cursor(next_off) if has_more else None,
            has_more=has_more,
        )

    def get_for_job(self, job: Job, *, aisle_id: str, artifact_id: str) -> JobArtifactView | None:
        for item in self._collect(job, aisle_id=aisle_id):
            if item.id == artifact_id:
                return item
        return None

    def _collect(self, job: Job, *, aisle_id: str) -> list[JobArtifactView]:
        out: list[JobArtifactView] = []
        out.extend(self._from_manifest(job))
        out.extend(self._from_durable_result_json(job))
        out.extend(self._from_source_assets(job, aisle_id=aisle_id))
        # De-dupe by id (manifest wins over result_json duplicates).
        by_id: dict[str, JobArtifactView] = {}
        for item in out:
            prev = by_id.get(item.id)
            if prev is None or (
                prev.status != ArtifactAvailabilityStatus.AVAILABLE
                and item.status == ArtifactAvailabilityStatus.AVAILABLE
            ):
                by_id[item.id] = item
        return list(by_id.values())

    def _from_manifest(self, job: Job) -> list[JobArtifactView]:
        if self._manifest is None:
            return []
        items: list[JobArtifactView] = []
        for entry in self._manifest.list_entries(job.id):
            category = _KIND_CATEGORY.get(entry.artifact_kind, ArtifactCategory.DEBUG)
            status = _manifest_status(entry)
            mime = _KIND_MIME.get(entry.artifact_kind)
            previewable = status == ArtifactAvailabilityStatus.AVAILABLE and (
                (mime or "").startswith("image/")
                or (mime or "") in {"application/json", "application/x-ndjson", "text/csv", "text/plain"}
            )
            items.append(
                JobArtifactView(
                    id=_artifact_id(job_id=job.id, kind=entry.artifact_kind),
                    job_id=job.id,
                    category=category,
                    kind=entry.artifact_kind,
                    stage="finalization",
                    display_name=entry.artifact_kind.replace("_", " ").title(),
                    original_filename=None,
                    mime_type=mime,
                    size_bytes=entry.size_bytes,
                    checksum=entry.source_sha256 or entry.content_hash,
                    width=None,
                    height=None,
                    status=status,
                    is_current=True,
                    is_previewable=previewable,
                    is_downloadable=status == ArtifactAvailabilityStatus.AVAILABLE,
                    created_at=entry.created_at,
                    published_at=entry.published_at,
                    expires_at=None,
                    source_type="generated",
                    source_asset_id=None,
                    storage_key=entry.storage_key,
                )
            )
        return items

    def _from_durable_result_json(self, job: Job) -> list[JobArtifactView]:
        """Fallback when manifest is empty but result_json.durable_artifacts exists."""
        result = job.result_json or {}
        durable = result.get("durable_artifacts")
        if not isinstance(durable, dict):
            return []
        items: list[JobArtifactView] = []
        for kind, meta in durable.items():
            if not isinstance(kind, str) or not isinstance(meta, dict):
                continue
            key = meta.get("storage_key") or meta.get("key")
            if not isinstance(key, str) or not key.strip():
                continue
            # Skip if already represented via manifest id.
            category = _KIND_CATEGORY.get(kind, ArtifactCategory.DEBUG)
            mime = _KIND_MIME.get(kind) or meta.get("content_type")
            if isinstance(mime, str):
                mime_s = mime
            else:
                mime_s = None
            size = meta.get("size_bytes")
            size_i = int(size) if isinstance(size, (int, float)) else None
            items.append(
                JobArtifactView(
                    id=_artifact_id(job_id=job.id, kind=kind),
                    job_id=job.id,
                    category=category,
                    kind=kind,
                    stage="finalization",
                    display_name=kind.replace("_", " ").title(),
                    original_filename=None,
                    mime_type=mime_s,
                    size_bytes=size_i,
                    checksum=str(meta.get("checksum")) if meta.get("checksum") else None,
                    width=None,
                    height=None,
                    status=ArtifactAvailabilityStatus.AVAILABLE,
                    is_current=True,
                    is_previewable=True,
                    is_downloadable=True,
                    created_at=job.finished_at or job.updated_at,
                    published_at=job.artifacts_published_at,
                    expires_at=None,
                    source_type="generated",
                    source_asset_id=None,
                    storage_key=key.strip(),
                )
            )
        return items

    def _from_source_assets(self, job: Job, *, aisle_id: str) -> list[JobArtifactView]:
        if self._assets is None:
            return []
        try:
            assets = list(self._assets.list_by_aisle(aisle_id))
        except Exception:
            return []
        items: list[JobArtifactView] = []
        for asset in assets:
            kind = (
                "source_video"
                if asset.type == SourceAssetType.VIDEO
                else "source_image"
            )
            mime = asset.mime_type or asset.content_type
            fname = asset.original_filename
            size = asset.file_size_bytes
            created = asset.uploaded_at
            storage_key = asset.storage_key
            items.append(
                JobArtifactView(
                    id=_artifact_id(
                        job_id=job.id, kind=kind, source_asset_id=str(asset.id)
                    ),
                    job_id=job.id,
                    category=ArtifactCategory.INPUT,
                    kind=kind,
                    stage="input",
                    display_name=str(fname or asset.id),
                    original_filename=str(fname) if fname else None,
                    mime_type=str(mime) if mime else None,
                    size_bytes=int(size) if isinstance(size, (int, float)) else None,
                    checksum=None,
                    width=None,
                    height=None,
                    status=ArtifactAvailabilityStatus.AVAILABLE,
                    is_current=True,
                    is_previewable=bool(mime and str(mime).startswith("image/")),
                    is_downloadable=True,
                    created_at=created if isinstance(created, datetime) else None,
                    published_at=None,
                    expires_at=None,
                    source_type="source_asset",
                    source_asset_id=str(asset.id),
                    storage_key=str(storage_key) if storage_key else None,
                )
            )
        return items


def assert_job_owned_storage_key(*, job_id: str, storage_key: str) -> None:
    """Reject storage keys that do not belong to the job namespace."""
    key = (storage_key or "").strip().lstrip("/")
    prefix = f"jobs/{job_id}/"
    if not key.startswith(prefix):
        raise ValueError(f"storage_key outside job namespace for job_id={job_id}")


def stable_content_token(*parts: Any) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p).encode("utf-8"))
        h.update(b"|")
    return h.hexdigest()[:16]
