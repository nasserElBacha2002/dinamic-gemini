"""Unified read model for Observability job artifacts (manifest + job input snapshot)."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid5

from src.application.ports.artifact_manifest_store import ArtifactManifestStore
from src.application.ports.job_source_asset_repository import JobSourceAssetRepository
from src.application.services.execution_log_incremental import InvalidCursorError
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
    UNKNOWN = "UNKNOWN"
    LEGACY_UNVERIFIED = "LEGACY_UNVERIFIED"


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

_KIND_FILENAME: dict[str, str] = {
    ARTIFACT_KIND_EXECUTION_LOG: "execution_log.jsonl",
    ARTIFACT_KIND_HYBRID_REPORT_JSON: "hybrid_report.json",
    ARTIFACT_KIND_HYBRID_REPORT_CSV: "hybrid_report.csv",
    ARTIFACT_KIND_TRACEABILITY_MANIFEST: "traceability_manifest.json",
}

_MIME_TO_EXT: dict[str, str] = {
    "application/json": "json",
    "application/x-ndjson": "jsonl",
    "application/ndjson": "jsonl",
    "text/csv": "csv",
    "text/plain": "txt",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "heic",
    "video/mp4": "mp4",
    "video/quicktime": "mov",
    "application/zip": "zip",
    "application/pdf": "pdf",
}

_ARTIFACT_NS = UUID("a7e2c4b1-9f33-4d8e-8c1a-0b6f5e4d3c2a")


def _basename_with_extension(name: str | None) -> str | None:
    raw = (name or "").strip().replace("\\", "/").split("/")[-1]
    if not raw or raw in {".", ".."}:
        return None
    if "." not in raw or raw.startswith("."):
        return None
    return raw


def resolve_artifact_download_filename(
    *,
    kind: str,
    original_filename: str | None = None,
    mime_type: str | None = None,
    storage_key: str | None = None,
) -> str:
    """Prefer original name, then storage-key basename, then kind/mime defaults."""
    for candidate in (original_filename, storage_key):
        base = _basename_with_extension(candidate)
        if base:
            return base
    mapped = _KIND_FILENAME.get(kind)
    if mapped:
        return mapped
    mime = (mime_type or "").strip().lower().split(";", 1)[0].strip()
    ext = _MIME_TO_EXT.get(mime)
    safe_kind = "".join(c for c in (kind or "artifact") if c.isalnum() or c in ("-", "_")) or "artifact"
    if ext:
        return f"{safe_kind}.{ext}"
    return f"{safe_kind}.bin"


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
    version: int = 1
    replaced_by_id: str | None = None
    # Internal only — never serialize to API responses.
    storage_key: str | None = None


@dataclass(frozen=True)
class JobArtifactPage:
    items: list[JobArtifactView]
    next_cursor: str | None
    has_more: bool
    inputs_legacy_unverified: bool = False


def _manifest_status(entry: ArtifactManifestEntry) -> ArtifactAvailabilityStatus:
    if entry.status == ArtifactManifestStatus.PUBLISHED:
        if not (entry.storage_key or "").strip():
            return ArtifactAvailabilityStatus.MISSING
        return ArtifactAvailabilityStatus.AVAILABLE
    if entry.status == ArtifactManifestStatus.FAILED:
        return ArtifactAvailabilityStatus.PUBLISH_FAILED
    if entry.status == ArtifactManifestStatus.PENDING:
        return ArtifactAvailabilityStatus.PENDING
    if entry.status == ArtifactManifestStatus.UNKNOWN:
        return ArtifactAvailabilityStatus.UNKNOWN
    return ArtifactAvailabilityStatus.MISSING


def artifact_id_from_parts(
    *,
    job_id: str,
    kind: str,
    storage_key: str | None = None,
    checksum: str | None = None,
    version: int = 1,
    source_asset_id: str | None = None,
    link_id: str | None = None,
) -> str:
    """Stable id that distinguishes versions of the same kind."""
    if link_id:
        return str(uuid5(_ARTIFACT_NS, f"link:{link_id}"))
    seed = (
        f"{job_id}|{kind}|v{int(version)}|"
        f"{(storage_key or '').strip()}|{(checksum or '').strip()}|"
        f"{source_asset_id or ''}"
    )
    return str(uuid5(_ARTIFACT_NS, seed))


def encode_artifact_cursor(
    offset: int,
    *,
    job_id: str,
    filters_fp: str,
) -> str:
    payload = {"v": 1, "job": job_id, "o": int(offset), "f": filters_fp}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_artifact_cursor(
    cursor: str | None,
    *,
    job_id: str,
    filters_fp: str,
) -> int:
    if not cursor:
        return 0
    try:
        pad = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(cursor + pad)
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise InvalidCursorError("INVALID_CURSOR") from exc
    if not isinstance(payload, dict) or payload.get("v") != 1:
        raise InvalidCursorError("INVALID_CURSOR")
    if payload.get("job") != job_id or payload.get("f") != filters_fp:
        raise InvalidCursorError("INVALID_CURSOR")
    try:
        return max(0, int(payload["o"]))
    except Exception as exc:
        raise InvalidCursorError("INVALID_CURSOR") from exc


def artifact_filters_fingerprint(
    *,
    category: str | None,
    kind: str | None,
    status: str | None,
    is_current: bool | None,
) -> str:
    raw = json.dumps(
        {
            "category": (category or "").strip().upper(),
            "kind": (kind or "").strip(),
            "status": (status or "").strip().upper(),
            "is_current": is_current,
        },
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class JobArtifactCatalogService:
    """Assemble Observability artifact catalog for one job without exposing storage keys."""

    def __init__(
        self,
        *,
        manifest_store: ArtifactManifestStore | None,
        job_source_asset_repo: JobSourceAssetRepository | None,
    ) -> None:
        self._manifest = manifest_store
        self._job_assets = job_source_asset_repo

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
        _ = aisle_id  # kept for route compatibility; inputs come from job snapshot.
        items, legacy = self._collect(job)
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

        items.sort(key=lambda a: (a.category.value, a.kind, a.version, a.id))
        filters_fp = artifact_filters_fingerprint(
            category=category, kind=kind, status=status, is_current=is_current
        )
        offset = decode_artifact_cursor(cursor, job_id=job.id, filters_fp=filters_fp)
        limit = max(1, min(int(limit), 200))
        window = items[offset : offset + limit]
        next_off = offset + len(window)
        has_more = next_off < len(items)
        return JobArtifactPage(
            items=window,
            next_cursor=(
                encode_artifact_cursor(next_off, job_id=job.id, filters_fp=filters_fp)
                if has_more
                else None
            ),
            has_more=has_more,
            inputs_legacy_unverified=legacy,
        )

    def get_for_job(self, job: Job, *, aisle_id: str, artifact_id: str) -> JobArtifactView | None:
        items, _ = self._collect(job)
        for item in items:
            if item.id == artifact_id:
                return item
        return None

    def _collect(self, job: Job) -> tuple[list[JobArtifactView], bool]:
        out: list[JobArtifactView] = []
        out.extend(self._from_manifest(job))
        out.extend(self._from_durable_result_json(job))
        inputs, legacy = self._from_job_source_assets(job)
        out.extend(inputs)
        # De-dupe by id only (do not collapse distinct versions of same kind).
        by_id: dict[str, JobArtifactView] = {}
        for item in out:
            by_id.setdefault(item.id, item)
        return list(by_id.values()), legacy

    def _from_manifest(self, job: Job) -> list[JobArtifactView]:
        if self._manifest is None:
            return []
        items: list[JobArtifactView] = []
        # Group by kind to mark current = highest version published.
        by_kind: dict[str, list[ArtifactManifestEntry]] = {}
        for entry in self._manifest.list_entries(job.id):
            by_kind.setdefault(entry.artifact_kind, []).append(entry)
        for kind, entries in by_kind.items():
            entries_sorted = sorted(entries, key=lambda e: int(e.version or 1))
            current_version = max(int(e.version or 1) for e in entries_sorted)
            for entry in entries_sorted:
                version = int(entry.version or 1)
                status = _manifest_status(entry)
                mime = _KIND_MIME.get(entry.artifact_kind)
                previewable = status == ArtifactAvailabilityStatus.AVAILABLE and (
                    (mime or "").startswith("image/")
                    or (mime or "")
                    in {"application/json", "application/x-ndjson", "text/csv", "text/plain"}
                )
                items.append(
                    JobArtifactView(
                        id=artifact_id_from_parts(
                            job_id=job.id,
                            kind=entry.artifact_kind,
                            storage_key=entry.storage_key,
                            checksum=entry.source_sha256 or entry.content_hash,
                            version=version,
                        ),
                        job_id=job.id,
                        category=_KIND_CATEGORY.get(kind, ArtifactCategory.DEBUG),
                        kind=kind,
                        stage="finalization",
                        display_name=kind.replace("_", " ").title(),
                        original_filename=resolve_artifact_download_filename(
                            kind=kind,
                            mime_type=mime,
                            storage_key=entry.storage_key,
                        ),
                        mime_type=mime,
                        size_bytes=entry.size_bytes,
                        checksum=entry.source_sha256 or entry.content_hash,
                        width=None,
                        height=None,
                        status=status,
                        is_current=version == current_version
                        and status == ArtifactAvailabilityStatus.AVAILABLE,
                        is_previewable=previewable,
                        is_downloadable=status == ArtifactAvailabilityStatus.AVAILABLE
                        and bool((entry.storage_key or "").strip()),
                        created_at=entry.created_at,
                        published_at=entry.published_at,
                        expires_at=None,
                        source_type="generated",
                        source_asset_id=None,
                        version=version,
                        storage_key=entry.storage_key,
                    )
                )
        return items

    def _from_durable_result_json(self, job: Job) -> list[JobArtifactView]:
        result = job.result_json or {}
        durable = result.get("durable_artifacts")
        if not isinstance(durable, dict):
            return []
        # Skip kinds already present from manifest.
        existing_kinds: set[str] = set()
        if self._manifest is not None:
            existing_kinds = {e.artifact_kind for e in self._manifest.list_entries(job.id)}
        items: list[JobArtifactView] = []
        for kind, meta in durable.items():
            if not isinstance(kind, str) or not isinstance(meta, dict):
                continue
            if kind in existing_kinds:
                continue
            key = meta.get("storage_key") or meta.get("key")
            if not isinstance(key, str) or not key.strip():
                status = ArtifactAvailabilityStatus.MISSING
                key_s = None
            else:
                key_s = key.strip()
                status = ArtifactAvailabilityStatus.AVAILABLE
            checksum = str(meta.get("checksum")) if meta.get("checksum") else None
            version = int(meta.get("version") or 1)
            mime = _KIND_MIME.get(kind) or meta.get("content_type")
            mime_s = mime if isinstance(mime, str) else None
            size = meta.get("size_bytes")
            size_i = int(size) if isinstance(size, (int, float)) else None
            items.append(
                JobArtifactView(
                    id=artifact_id_from_parts(
                        job_id=job.id,
                        kind=kind,
                        storage_key=key_s,
                        checksum=checksum,
                        version=version,
                    ),
                    job_id=job.id,
                    category=_KIND_CATEGORY.get(kind, ArtifactCategory.DEBUG),
                    kind=kind,
                    stage="finalization",
                    display_name=kind.replace("_", " ").title(),
                    original_filename=resolve_artifact_download_filename(
                        kind=kind,
                        mime_type=mime_s,
                        storage_key=key_s,
                    ),
                    mime_type=mime_s,
                    size_bytes=size_i,
                    checksum=checksum,
                    width=None,
                    height=None,
                    status=status,
                    is_current=status == ArtifactAvailabilityStatus.AVAILABLE,
                    is_previewable=status == ArtifactAvailabilityStatus.AVAILABLE,
                    is_downloadable=status == ArtifactAvailabilityStatus.AVAILABLE and bool(key_s),
                    created_at=job.finished_at or job.updated_at,
                    published_at=job.artifacts_published_at,
                    expires_at=None,
                    source_type="generated",
                    source_asset_id=None,
                    version=version,
                    storage_key=key_s,
                )
            )
        return items

    def _from_job_source_assets(self, job: Job) -> tuple[list[JobArtifactView], bool]:
        if self._job_assets is None:
            # No snapshot store — do not invent aisle-wide assets.
            return [], True
        links = self._job_assets.list_for_job(job.id)
        if not links:
            return [], True
        items: list[JobArtifactView] = []
        for link in links:
            kind = "source_video" if link.asset_role == "video" else (
                "reference_image" if link.asset_role == "reference" else "source_image"
            )
            has_key = bool((link.storage_key or "").strip())
            status = (
                ArtifactAvailabilityStatus.AVAILABLE
                if has_key
                else ArtifactAvailabilityStatus.MISSING
            )
            items.append(
                JobArtifactView(
                    id=artifact_id_from_parts(
                        job_id=job.id,
                        kind=kind,
                        storage_key=link.storage_key,
                        checksum=link.checksum,
                        version=1,
                        source_asset_id=link.source_asset_id,
                        link_id=link.id,
                    ),
                    job_id=job.id,
                    category=ArtifactCategory.INPUT,
                    kind=kind,
                    stage=link.stage or "input",
                    display_name=f"{link.asset_role}:{link.source_asset_id}",
                    original_filename=resolve_artifact_download_filename(
                        kind=kind,
                        original_filename=link.original_filename,
                        mime_type=link.mime_type,
                        storage_key=link.storage_key,
                    ),
                    mime_type=link.mime_type,
                    size_bytes=link.size_bytes,
                    checksum=link.checksum,
                    width=link.width,
                    height=link.height,
                    status=status,
                    is_current=True,
                    is_previewable=bool(link.mime_type and link.mime_type.startswith("image/"))
                    and status == ArtifactAvailabilityStatus.AVAILABLE,
                    is_downloadable=status == ArtifactAvailabilityStatus.AVAILABLE,
                    created_at=link.created_at,
                    published_at=None,
                    expires_at=None,
                    source_type="job_source_asset",
                    source_asset_id=link.source_asset_id,
                    version=1,
                    storage_key=link.storage_key,
                )
            )
        return items, False


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
