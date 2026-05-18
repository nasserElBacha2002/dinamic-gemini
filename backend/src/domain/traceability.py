"""
Traceability of counted results to source images (Epic 3.1.B).

Validates source_image_id against primary frames sent to the model and
assigns a structured traceability status to each entity.

Diagnostic policy (Epic 3.1.C):
- traceability_warning is diagnostic only: exposed in report and API (EntityListItem).
- It is NOT persisted to pallet_results. Use it for review/audit and filtering.
- Persisted fields: source_image_id, traceability_status only.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from src.domain.entity import Entity


class TraceabilityStatus(str, Enum):
    """Allowed traceability status values. Use .value for persistence/API."""

    VALID = "valid"  # source_image_id present and in sent primary model input frames
    MISSING = "missing"  # source_image_id absent or empty
    INVALID = "invalid"  # source_image_id present but not in sent primary frames (context was available)
    UNVALIDATED = "unvalidated"  # source_image_id present but validation context was not available


# Convenience constants for backward-compatible string comparison
TRACEABILITY_VALID = TraceabilityStatus.VALID.value
TRACEABILITY_MISSING = TraceabilityStatus.MISSING.value
TRACEABILITY_INVALID = TraceabilityStatus.INVALID.value
TRACEABILITY_UNVALIDATED = TraceabilityStatus.UNVALIDATED.value


def apply_traceability_validation(
    entities: list[Entity],
    valid_image_ids: frozenset[str],
    *,
    manifest_image_ids: frozenset[str] | None = None,
) -> None:
    """Set traceability_status and traceability_warning on each entity in place.

    When validation context is available (valid_image_ids is non-empty):
    - source_image_id present and in valid_image_ids -> valid
    - source_image_id absent or empty -> missing
    - source_image_id present but not in valid_image_ids -> invalid (warning set)

    ``valid_image_ids`` should be the primary frames actually sent to the model (Phase 1).
    When ``manifest_image_ids`` is provided, IDs in the manifest but not in ``valid_image_ids``
    receive a distinct warning (not part of model input frames).

    When validation context is missing (valid_image_ids is empty), we avoid
    marking references as invalid merely because context could not be established:
    - source_image_id absent or empty -> missing
    - source_image_id present -> unvalidated (no warning; we did not validate)
    """
    has_context = len(valid_image_ids) > 0
    manifest = manifest_image_ids or frozenset()

    for ent in entities:
        sid = getattr(ent, "source_image_id", None)
        sid = (sid or "").strip() if sid else ""

        if not sid:
            ent.traceability_status = TraceabilityStatus.MISSING.value
            ent.traceability_warning = None
            continue

        if has_context:
            if sid in valid_image_ids:
                ent.traceability_status = TraceabilityStatus.VALID.value
                ent.traceability_warning = None
            else:
                ent.traceability_status = TraceabilityStatus.INVALID.value
                if manifest and sid in manifest:
                    ent.traceability_warning = (
                        f"source_image_id was not part of the model input frames: {sid!r}"
                    )
                else:
                    ent.traceability_warning = f"source_image_id not in job: {sid!r}"
        else:
            ent.traceability_status = TraceabilityStatus.UNVALIDATED.value
            ent.traceability_warning = None


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
