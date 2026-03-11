"""
Traceability of counted results to source images (Epic 3.1.B).

Validates source_image_id against the current job's registered images and
assigns a structured traceability status to each entity.

Semantics:
- We only mark a reference as INVALID when we have a reliable validation context
  (non-empty valid_image_ids). When context is missing (e.g. video job, manifest
  unavailable), we use UNVALIDATED for present source_image_id to avoid false negatives.
"""

from enum import Enum
from typing import List

from src.domain.entity import Entity


class TraceabilityStatus(str, Enum):
    """Allowed traceability status values. Use .value for persistence/API."""

    VALID = "valid"  # source_image_id present and in job's registered images
    MISSING = "missing"  # source_image_id absent or empty
    INVALID = "invalid"  # source_image_id present but not in job's registered images (context was available)
    UNVALIDATED = "unvalidated"  # source_image_id present but validation context was not available


# Convenience constants for backward-compatible string comparison
TRACEABILITY_VALID = TraceabilityStatus.VALID.value
TRACEABILITY_MISSING = TraceabilityStatus.MISSING.value
TRACEABILITY_INVALID = TraceabilityStatus.INVALID.value
TRACEABILITY_UNVALIDATED = TraceabilityStatus.UNVALIDATED.value


def apply_traceability_validation(
    entities: List[Entity],
    valid_image_ids: frozenset[str],
) -> None:
    """Set traceability_status and traceability_warning on each entity in place.

    When validation context is available (valid_image_ids is non-empty):
    - source_image_id present and in valid_image_ids -> valid
    - source_image_id absent or empty -> missing
    - source_image_id present but not in valid_image_ids -> invalid (warning set)

    When validation context is missing (valid_image_ids is empty), we avoid
    marking references as invalid merely because context could not be established:
    - source_image_id absent or empty -> missing
    - source_image_id present -> unvalidated (no warning; we did not validate)
    """
    has_context = len(valid_image_ids) > 0

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
                ent.traceability_warning = f"source_image_id not in job: {sid!r}"
        else:
            ent.traceability_status = TraceabilityStatus.UNVALIDATED.value
            ent.traceability_warning = None
