"""Canonical resolution of job photos → linked positions (image coverage).

Join keys (in order of preference per evidence row):
- ``result_evidence.source_asset_id`` matching ``job_source_assets.source_asset_id``
- ``result_evidence.source_image_id`` matching ``job_source_assets.source_asset_id``
  (pipeline often uses asset id as source_image_id)
- Fallback: ``positions.detected_summary_json.source_image_id`` / ``source_asset_id``

Does not assume 1:1 image↔position. One image may map to many positions.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from src.application.ports.job_source_asset_repository import JobSourceAssetLink
from src.domain.jobs.entities import Job, JobStatus
from src.domain.positions.entities import Position, PositionCreationSource
from src.domain.result_evidence.entities import ResultEvidenceRecord

#: Snapshot roles treated as aisle photo inputs for coverage (exclude video/frame/reference).
PHOTO_COVERAGE_ASSET_ROLES = frozenset({"primary"})


class ImageProcessingPresentationStatus(str, Enum):
    """Presentation-only status for the image-coverage API (not a persisted state machine)."""

    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED_WITH_RESULT = "processed_with_result"
    PROCESSED_WITHOUT_RESULT = "processed_without_result"
    FAILED = "failed"


@dataclass(frozen=True)
class JobPhotoCoverageImage:
    """One unique photo from the job snapshot (deduped by source_asset_id)."""

    job_source_asset_id: str
    source_asset_id: str
    job_id: str
    original_filename: str | None
    created_at: datetime
    position_order: int
    mime_type: str | None
    storage_key: str | None


@dataclass(frozen=True)
class ImageResultOriginCounts:
    automatic_result_count: int
    manual_result_count: int
    has_manual_result: bool


def job_has_video_snapshot(links: Sequence[JobSourceAssetLink]) -> bool:
    return any((link.asset_role or "").strip().lower() == "video" for link in links)


def is_photos_job_snapshot(links: Sequence[JobSourceAssetLink], job: Job | None = None) -> bool:
    """True when the job is treated as a photos run for image-coverage APIs.

    Prefers ``payload_json.input_type`` when present; otherwise infers from snapshot roles
    (no ``video`` role ⇒ photos).
    """
    if job is not None:
        payload = job.payload_json if isinstance(job.payload_json, dict) else {}
        raw = payload.get("input_type")
        if isinstance(raw, str) and raw.strip():
            return raw.strip().lower() == "photos"
    if not links:
        return False
    return not job_has_video_snapshot(links)


def unique_photo_coverage_images(links: Sequence[JobSourceAssetLink]) -> list[JobPhotoCoverageImage]:
    """Dedupe snapshot links to one row per ``source_asset_id`` (primary photos only)."""
    photos = [
        link
        for link in links
        if (link.asset_role or "").strip().lower() in PHOTO_COVERAGE_ASSET_ROLES
    ]
    by_asset: dict[str, JobSourceAssetLink] = {}
    for link in sorted(photos, key=lambda x: (x.position_order, x.id)):
        aid = (link.source_asset_id or "").strip()
        if not aid or aid in by_asset:
            continue
        by_asset[aid] = link
    out: list[JobPhotoCoverageImage] = []
    for link in sorted(by_asset.values(), key=lambda x: (x.position_order, x.source_asset_id)):
        out.append(
            JobPhotoCoverageImage(
                job_source_asset_id=link.id,
                source_asset_id=link.source_asset_id,
                job_id=link.job_id,
                original_filename=link.original_filename,
                created_at=link.created_at,
                position_order=link.position_order,
                mime_type=link.mime_type,
                storage_key=link.storage_key,
            )
        )
    return out


def index_positions_by_source_asset(
    *,
    coverage_asset_ids: frozenset[str],
    result_evidence: Sequence[ResultEvidenceRecord],
    positions: Sequence[Position],
) -> dict[str, list[Position]]:
    """Map ``source_asset_id`` → linked positions (stable order by position id)."""
    pos_by_id = {p.id: p for p in positions}
    linked: dict[str, set[str]] = defaultdict(set)

    for row in result_evidence:
        pid = (row.position_id or "").strip()
        if not pid or pid not in pos_by_id:
            continue
        for candidate in (row.source_asset_id, row.source_image_id):
            cid = (candidate or "").strip()
            if cid and cid in coverage_asset_ids:
                linked[cid].add(pid)

    for position in positions:
        summary = position.detected_summary_json if isinstance(position.detected_summary_json, dict) else {}
        for key in ("source_asset_id", "source_image_id"):
            raw = summary.get(key)
            if not isinstance(raw, str):
                continue
            cid = raw.strip()
            if cid and cid in coverage_asset_ids:
                linked[cid].add(position.id)

    return {
        asset_id: [pos_by_id[pid] for pid in sorted(pids) if pid in pos_by_id]
        for asset_id, pids in linked.items()
    }


def count_linked_positions_for_asset(
    *,
    source_asset_id: str,
    coverage_asset_ids: frozenset[str],
    result_evidence: Sequence[ResultEvidenceRecord],
    positions: Sequence[Position],
) -> int:
    indexed = index_positions_by_source_asset(
        coverage_asset_ids=coverage_asset_ids,
        result_evidence=result_evidence,
        positions=positions,
    )
    return len(indexed.get(source_asset_id, ()))


def resolve_result_origin_counts(positions: Sequence[Position]) -> ImageResultOriginCounts:
    manual = sum(1 for p in positions if p.creation_source == PositionCreationSource.MANUAL)
    automatic = len(positions) - manual
    return ImageResultOriginCounts(
        automatic_result_count=automatic,
        manual_result_count=manual,
        has_manual_result=manual > 0,
    )


def resolve_image_processing_status(
    *,
    job: Job,
    result_count: int,
) -> ImageProcessingPresentationStatus:
    """Derive presentation status from job lifecycle + linked results."""
    status = job.status
    if status in (JobStatus.QUEUED, JobStatus.STARTING):
        return ImageProcessingPresentationStatus.PENDING
    if status in (JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED):
        return ImageProcessingPresentationStatus.PROCESSING
    if status == JobStatus.FAILED:
        return ImageProcessingPresentationStatus.FAILED
    if result_count > 0:
        return ImageProcessingPresentationStatus.PROCESSED_WITH_RESULT
    return ImageProcessingPresentationStatus.PROCESSED_WITHOUT_RESULT


def position_has_manual_creation(position: Position) -> bool:
    return position.creation_source == PositionCreationSource.MANUAL
