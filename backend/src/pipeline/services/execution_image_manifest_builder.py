"""
Phase 4.3 — Build canonical ExecutionImageManifest from final photo execution inputs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.domain.execution_image_manifest import (
    ExcludedExecutionImage,
    ExecutionImageEntry,
    ExecutionImageManifest,
    ExecutionImageManifestError,
    ExecutionImageRole,
    ImageExclusionReason,
    validate_execution_image_manifest,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ManifestPrimaryCandidate:
    source_image_id: str
    source_asset_id: str
    storage_reference: str
    original_filename: str | None = None
    mime_type: str | None = None


@dataclass(frozen=True)
class ManifestReferenceCandidate:
    source_image_id: str
    source_asset_id: str
    storage_reference: str
    original_filename: str | None = None
    mime_type: str | None = None
    loaded: bool = True


def _primary_entry_id(index_1based: int) -> str:
    return f"IMG_{index_1based:03d}"


def _reference_entry_id(index_1based: int) -> str:
    return f"REF_{index_1based:03d}"


def build_execution_image_manifest(
    *,
    job_id: str,
    primary_candidates: list[ManifestPrimaryCandidate],
    reference_candidates: list[ManifestReferenceCandidate],
    excluded: list[ExcludedExecutionImage] | None = None,
) -> ExecutionImageManifest:
    """
    Build the canonical manifest after the final image set is known.

    Reference entries are ordered before primary entries in ``payload_ordinal`` to
  match provider multimodal ordering (references, then aisle evidence).
    """
    excluded_entries = tuple(excluded or [])
    excluded_ids = frozenset(e.source_image_id for e in excluded_entries)

    entries: list[ExecutionImageEntry] = []
    ordinal = 1

    seen_ref: set[str] = set()
    ref_index = 0
    for cand in reference_candidates:
        sid = (cand.source_image_id or "").strip()
        if not sid:
            continue
        if not cand.loaded:
            excluded_entries = excluded_entries + (
                ExcludedExecutionImage(
                    source_asset_id=cand.source_asset_id or sid,
                    source_image_id=sid,
                    reason=ImageExclusionReason.MISSING_STORAGE_OBJECT,
                    original_filename=cand.original_filename,
                ),
            )
            excluded_ids = frozenset(e.source_image_id for e in excluded_entries)
            continue
        if sid in excluded_ids or sid in seen_ref:
            continue
        ref_index += 1
        seen_ref.add(sid)
        entries.append(
            ExecutionImageEntry(
                manifest_entry_id=_reference_entry_id(ref_index),
                source_asset_id=(cand.source_asset_id or sid).strip(),
                source_image_id=sid,
                role=ExecutionImageRole.REFERENCE_IMAGE,
                payload_ordinal=ordinal,
                storage_reference=cand.storage_reference,
                original_filename=cand.original_filename,
                mime_type=cand.mime_type,
            )
        )
        ordinal += 1

    seen_primary: set[str] = set()
    primary_index = 0
    for cand in primary_candidates:
        sid = (cand.source_image_id or "").strip()
        if not sid:
            raise ExecutionImageManifestError("primary candidate missing source_image_id")
        if sid in excluded_ids:
            continue
        if sid in seen_primary:
            excluded_entries = excluded_entries + (
                ExcludedExecutionImage(
                    source_asset_id=cand.source_asset_id or sid,
                    source_image_id=sid,
                    reason=ImageExclusionReason.DUPLICATE,
                    original_filename=cand.original_filename,
                ),
            )
            excluded_ids = frozenset(e.source_image_id for e in excluded_entries)
            continue
        primary_index += 1
        seen_primary.add(sid)
        entries.append(
            ExecutionImageEntry(
                manifest_entry_id=_primary_entry_id(primary_index),
                source_asset_id=(cand.source_asset_id or sid).strip(),
                source_image_id=sid,
                role=ExecutionImageRole.PRIMARY_EVIDENCE,
                payload_ordinal=ordinal,
                storage_reference=cand.storage_reference,
                original_filename=cand.original_filename,
                mime_type=cand.mime_type,
            )
        )
        ordinal += 1

    manifest = ExecutionImageManifest(
        job_id=job_id,
        entries=tuple(entries),
        excluded_entries=excluded_entries,
    )
    validate_execution_image_manifest(manifest)
    return manifest


def exclusions_from_acquisition_metadata(
    metadata: dict[str, Any] | None,
) -> list[ExcludedExecutionImage]:
    """Parse exclusion records produced by ``FrameAcquisitionStage``."""
    if not metadata:
        return []
    raw = metadata.get("manifest_exclusions")
    if not isinstance(raw, list):
        return []
    out: list[ExcludedExecutionImage] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        reason_raw = str(item.get("reason") or "").strip()
        try:
            reason = ImageExclusionReason(reason_raw)
        except ValueError:
            reason = ImageExclusionReason.FILTERED
        sid = str(item.get("source_image_id") or "").strip()
        if not sid:
            continue
        out.append(
            ExcludedExecutionImage(
                source_asset_id=str(item.get("source_asset_id") or sid).strip(),
                source_image_id=sid,
                reason=reason,
                original_filename=(
                    str(item["original_filename"]).strip()
                    if item.get("original_filename") not in (None, "")
                    else None
                ),
            )
        )
    return out


def primary_candidates_from_acquired(
    frame_paths: list[Path],
    frame_refs: list[str],
) -> list[ManifestPrimaryCandidate]:
    candidates: list[ManifestPrimaryCandidate] = []
    for i, path in enumerate(frame_paths):
        ref = frame_refs[i].strip() if i < len(frame_refs) else ""
        if not ref:
            continue
        candidates.append(
            ManifestPrimaryCandidate(
                source_image_id=ref,
                source_asset_id=ref,
                storage_reference=path.name,
                original_filename=path.name,
            )
        )
    return candidates


def reference_candidates_from_visual_bundle(
    analysis_context: Any | None,
    resolved_reference_ids: list[str],
) -> list[ManifestReferenceCandidate]:
    if not analysis_context or not getattr(analysis_context, "visual_references", None):
        return []
    refs = list(analysis_context.visual_references)
    candidates: list[ManifestReferenceCandidate] = []
    resolved_set = frozenset(resolved_reference_ids)
    for ref in refs:
        rid = (ref.reference_id or "").strip()
        if not rid:
            continue
        path = (ref.resolved_path or ref.source_path or "").strip()
        candidates.append(
            ManifestReferenceCandidate(
                source_image_id=rid,
                source_asset_id=rid,
                storage_reference=Path(path).name if path else rid,
                original_filename=Path((ref.source_path or rid)).name or None,
                mime_type=getattr(ref, "mime_type", None),
                loaded=rid in resolved_set,
            )
        )
    return candidates


def log_manifest_diagnostics(
    *,
    manifest: ExecutionImageManifest,
    provider: str | None = None,
) -> None:
    """Structured manifest summary (no bytes, paths, or credentials)."""
    exclusion_counts: dict[str, int] = {}
    for ex in manifest.excluded_entries:
        key = ex.reason.value
        exclusion_counts[key] = exclusion_counts.get(key, 0) + 1
    logger.info(
        "execution_image_manifest job_id=%s version=%d provider=%s "
        "primary_count=%d reference_count=%d excluded_count=%d "
        "entry_ids=%s exclusion_reasons=%s",
        manifest.job_id,
        manifest.version,
        provider or "",
        len(manifest.primary_entries()),
        len(manifest.reference_entries()),
        len(manifest.excluded_entries),
        [e.manifest_entry_id for e in manifest.ordered_entries()],
        exclusion_counts,
    )
