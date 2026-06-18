"""
Traceability of counted results to source images (Epic 3.1.B, Phase 4.2).

Validates source_image_id against primary frames actually sent to the model and
assigns a structured traceability status to each entity.

Phase 4.2 policy:
- ``traceability_warning`` is persisted in ``detected_summary_json`` and exposed via API.
- Only ``traceability_status == valid`` with a present ``source_image_id`` may be
  treated as displayable evidence (see :func:`is_traceability_evidence_displayable`).
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from src.domain.entity import Entity

logger = logging.getLogger(__name__)

# Operational warnings (safe for API; no secrets or prompt text).
WARNING_NOT_IN_SENT = (
    "Returned image ID was not part of the final provider payload."
)
WARNING_NOT_IN_JOB = "Returned image ID is unknown for this job."
WARNING_REFERENCE_IMAGE = (
    "The referenced image is a supplier reference image and cannot be used as primary aisle evidence."
)
WARNING_MISSING_ID = "The provider did not return an evidence image ID."
WARNING_UNVALIDATED = (
    "Final sent-image metadata was unavailable, so the reference could not be validated."
)


class TraceabilityStatus(str, Enum):
    """Allowed traceability status values. Use .value for persistence/API."""

    VALID = "valid"  # source_image_id present and in sent primary model input frames
    MISSING = "missing"  # source_image_id absent or empty
    INVALID = "invalid"  # source_image_id present but not in sent primary frames (context was available)
    UNVALIDATED = (
        "unvalidated"  # source_image_id present but validation context was not available
    )


# Convenience constants for backward-compatible string comparison
TRACEABILITY_VALID = TraceabilityStatus.VALID.value
TRACEABILITY_MISSING = TraceabilityStatus.MISSING.value
TRACEABILITY_INVALID = TraceabilityStatus.INVALID.value
TRACEABILITY_UNVALIDATED = TraceabilityStatus.UNVALIDATED.value


def normalize_traceability_status(raw: object | None) -> str | None:
    """Return lowercase status string when known; otherwise None."""
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if s in ALL_TRACEABILITY_STATUSES:
        return s
    return None


def is_traceability_evidence_displayable(
    *,
    traceability_status: str | None,
    source_image_id: str | None,
) -> bool:
    """Central rule: evidence may be shown only when traceability is proven VALID.

    A resolvable ``source_image_id`` alone is never sufficient.
    """
    status = normalize_traceability_status(traceability_status)
    sid = (source_image_id or "").strip() if source_image_id else ""
    return status == TraceabilityStatus.VALID.value and bool(sid)


def extract_sent_image_ids_from_composition(
    composition: dict[str, Any] | None,
) -> frozenset[str] | None:
    """Return final sent primary IDs from canonical manifest or derived ``frames_sent_ids``.

    ``prompt_listed_image_ids`` is diagnostic only and must never authorize VALID traceability.
    When a serialized manifest key is present but invalid, fail closed (no legacy fallback).
    """
    from src.domain.execution_image_manifest import (
        ExecutionImageManifestError,
        composition_has_execution_image_manifest,
        require_manifest_from_composition,
    )

    if composition_has_execution_image_manifest(composition):
        try:
            manifest = require_manifest_from_composition(composition)
        except ExecutionImageManifestError:
            return None
        if manifest is None:
            return None
        ids = manifest.primary_source_image_ids()
        return frozenset(ids) if ids else None
    if not composition:
        return None
    sent_raw = composition.get("frames_sent_ids")
    if not isinstance(sent_raw, list):
        return None
    ids = frozenset(
        str(value).strip()
        for value in sent_raw
        if value is not None and str(value).strip()
    )
    return ids if ids else None


def resolve_has_valid_evidence_displayable(
    *,
    traceability_status: str | None,
    source_image_id: str | None,
    persisted_has_valid_evidence: object | None,
) -> bool:
    """Fail-closed: persisted ``has_valid_evidence`` must be explicitly ``True`` and derived rule must pass."""
    if persisted_has_valid_evidence is not True:
        return False
    return is_traceability_evidence_displayable(
        traceability_status=traceability_status,
        source_image_id=source_image_id,
    )


def extract_reference_image_ids(
    composition: dict[str, Any] | None,
    *,
    provider_metadata: dict[str, Any] | None = None,
) -> frozenset[str]:
    """Collect supplier/reference image IDs from manifest, composition, or provider metadata."""
    from src.domain.execution_image_manifest import (
        ExecutionImageManifestError,
        composition_has_execution_image_manifest,
        require_manifest_from_composition,
    )

    if composition_has_execution_image_manifest(composition):
        try:
            manifest = require_manifest_from_composition(composition)
        except ExecutionImageManifestError:
            return frozenset()
        if manifest is not None:
            return frozenset(manifest.reference_source_image_ids())
    refs: set[str] = set()
    if composition:
        raw = composition.get("reference_image_ids")
        if isinstance(raw, list):
            refs.update(str(x).strip() for x in raw if x is not None and str(x).strip())
    if provider_metadata:
        raw = provider_metadata.get("visual_reference_ids")
        if isinstance(raw, list):
            refs.update(str(x).strip() for x in raw if x is not None and str(x).strip())
    return frozenset(refs)


def apply_traceability_validation(
    entities: list[Entity],
    valid_image_ids: frozenset[str],
    *,
    manifest_image_ids: frozenset[str] | None = None,
    reference_image_ids: frozenset[str] | None = None,
    sent_metadata_available: bool = True,
) -> None:
    """Set traceability_status and traceability_warning on each entity in place.

    When ``sent_metadata_available`` is True and ``valid_image_ids`` is non-empty:
    - source_image_id present and in valid_image_ids (and not a reference ID) -> valid
    - source_image_id absent or empty -> missing (with warning)
    - source_image_id present but reference-only -> invalid
    - source_image_id present but not in valid_image_ids -> invalid (warning set)

  ``valid_image_ids`` must be the primary frames actually sent to the model (Phase 1).
    When ``manifest_image_ids`` is provided, IDs in the manifest but not in ``valid_image_ids``
    receive a distinct warning (not part of model input frames).

    When ``sent_metadata_available`` is False or ``valid_image_ids`` is empty:
    - source_image_id absent or empty -> missing
    - source_image_id present -> unvalidated (warning: metadata unavailable)
    """
    has_context = sent_metadata_available and len(valid_image_ids) > 0
    manifest = manifest_image_ids or frozenset()
    reference_ids = reference_image_ids or frozenset()

    for ent in entities:
        pre_status = normalize_traceability_status(getattr(ent, "traceability_status", None))
        if pre_status in (
            TraceabilityStatus.INVALID.value,
            TraceabilityStatus.MISSING.value,
            TraceabilityStatus.UNVALIDATED.value,
        ):
            continue

        sid = getattr(ent, "source_image_id", None)
        sid = (sid or "").strip() if sid else ""

        if not sid:
            raw_sid = getattr(ent, "raw_source_image_id", None)
            raw_sid = (raw_sid or "").strip() if raw_sid else ""
            if raw_sid and not has_context:
                ent.source_image_id = None
                ent.traceability_status = TraceabilityStatus.UNVALIDATED.value
                ent.traceability_warning = WARNING_UNVALIDATED
                continue
            ent.traceability_status = TraceabilityStatus.MISSING.value
            ent.traceability_warning = WARNING_MISSING_ID
            continue

        if reference_ids and sid in reference_ids:
            ent.traceability_status = TraceabilityStatus.INVALID.value
            ent.traceability_warning = WARNING_REFERENCE_IMAGE
            continue

        if has_context:
            if sid in valid_image_ids:
                ent.traceability_status = TraceabilityStatus.VALID.value
                ent.traceability_warning = None
            else:
                ent.traceability_status = TraceabilityStatus.INVALID.value
                if manifest and sid in manifest:
                    ent.traceability_warning = WARNING_NOT_IN_SENT
                else:
                    ent.traceability_warning = WARNING_NOT_IN_JOB
        else:
            ent.traceability_status = TraceabilityStatus.UNVALIDATED.value
            ent.traceability_warning = WARNING_UNVALIDATED


def log_traceability_validation_summary(
    *,
    job_id: str,
    entities: list[Entity],
    valid_image_ids: frozenset[str],
    sent_metadata_available: bool,
    provider: str | None = None,
) -> None:
    """Structured info log for traceability validation (no image bytes or prompts)."""
    counts = compute_traceability_summary(entities)
    logger.info(
        "traceability_validation job_id=%s provider=%s sent_metadata_available=%s "
        "final_sent_image_count=%d valid=%d invalid=%d missing=%d unvalidated=%d",
        job_id,
        provider or "",
        sent_metadata_available,
        len(valid_image_ids),
        counts["valid"],
        counts["invalid"],
        counts["missing"],
        counts["unvalidated"],
    )


# Epic 3.1.C — Review/audit summary (counts by traceability status)
ALL_TRACEABILITY_STATUSES = (
    TraceabilityStatus.VALID.value,
    TraceabilityStatus.MISSING.value,
    TraceabilityStatus.INVALID.value,
    TraceabilityStatus.UNVALIDATED.value,
)


def compute_traceability_summary(entities: list[Entity]) -> dict[str, int]:
    """Compute job-level traceability counts for review and audit.

    Returns a dict with keys: total_entities, valid, missing, invalid, unvalidated.

    Legacy/unknown policy: Entities without traceability_status, or with any value
    not in (valid, missing, invalid, unvalidated), are counted as missing. This
    ensures backward compatibility with pre-3.1.B jobs and avoids inflating
    "invalid" when the field is absent or non-standard.
    """
    counts: dict[str, int] = {
        "total_entities": len(entities),
        "valid": 0,
        "missing": 0,
        "invalid": 0,
        "unvalidated": 0,
    }
    for ent in entities:
        status = getattr(ent, "traceability_status", None) or ""
        status = (status or "").strip().lower()
        if status == TraceabilityStatus.VALID.value:
            counts["valid"] += 1
        elif status == TraceabilityStatus.MISSING.value:
            counts["missing"] += 1
        elif status == TraceabilityStatus.INVALID.value:
            counts["invalid"] += 1
        elif status == TraceabilityStatus.UNVALIDATED.value:
            counts["unvalidated"] += 1
        else:
            counts["missing"] += 1  # legacy or unknown -> treat as missing (documented policy)
    return counts


def compute_traceability_summary_from_entity_dicts(
    entity_dicts: list[dict[str, Any]],
) -> dict[str, int]:
    """Compute traceability summary from report-style entity dicts (no Domain Entity needed).

    Same counts and legacy/unknown policy as compute_traceability_summary.
    Use from API or report layer when only dict payloads are available.
    """
    counts: dict[str, int] = {
        "total_entities": len(entity_dicts),
        "valid": 0,
        "missing": 0,
        "invalid": 0,
        "unvalidated": 0,
    }
    for e in entity_dicts:
        status = (e.get("traceability_status") or "").strip().lower()
        if status == TraceabilityStatus.VALID.value:
            counts["valid"] += 1
        elif status == TraceabilityStatus.MISSING.value:
            counts["missing"] += 1
        elif status == TraceabilityStatus.INVALID.value:
            counts["invalid"] += 1
        elif status == TraceabilityStatus.UNVALIDATED.value:
            counts["unvalidated"] += 1
        else:
            counts["missing"] += 1  # legacy or unknown -> treat as missing (documented policy)
    return counts
