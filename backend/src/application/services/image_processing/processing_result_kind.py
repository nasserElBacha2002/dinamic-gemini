"""Semantic result kinds produced by code-scan recognition (runtime evidence only)."""

from __future__ import annotations

from typing import Literal

from src.domain.image_processing.contracts import ImageProcessingResult, ImageResultStatus

ProcessingResultKind = Literal[
    "PRODUCT",
    "POSITION_ONLY",
    "PRODUCT_WITH_POSITION",
    "UNRECOGNIZED",
    "MANUAL_REVIEW",
]

RESULT_KIND_POSITION_ONLY = "POSITION_ONLY"

_VALID_POSITION_STATUSES = frozenset({"VALID", "SIGNATURE_VALIDATION_SKIPPED"})


def get_result_kind(result: ImageProcessingResult) -> str | None:
    evidence = result.evidence if isinstance(result.evidence, dict) else {}
    kind = evidence.get("result_kind")
    if kind is None:
        return None
    text = str(kind).strip()
    return text or None


def requires_product_persistence(result: ImageProcessingResult) -> bool:
    """True when persistence must create product records (not position-only)."""
    kind = get_result_kind(result)
    if kind == RESULT_KIND_POSITION_ONLY:
        return False
    return True


def validate_position_only_evidence(result: ImageProcessingResult) -> tuple[bool, str | None]:
    """Fail-closed validation for POSITION_ONLY before acknowledging persistence."""
    if result.status not in (
        ImageResultStatus.RESOLVED_INTERNAL,
        ImageResultStatus.RESOLVED_EXTERNAL,
    ):
        return False, "not_resolved"

    if get_result_kind(result) != RESULT_KIND_POSITION_ONLY:
        return False, "not_position_only"

    evidence = result.evidence if isinstance(result.evidence, dict) else {}
    meta = evidence.get("position_label_detection")
    if not isinstance(meta, dict):
        return False, "missing_position_label_detection"

    statuses = meta.get("position_statuses") or []
    if not any(str(s) in _VALID_POSITION_STATUSES for s in statuses):
        return False, "invalid_position_status"

    normalized = meta.get("normalized_positions") or []
    if normalized:
        if not any(
            isinstance(row, dict) and (row.get("position_id") or "").strip()
            for row in normalized
        ):
            return False, "empty_position_id"
        return True, None

    detection_count = int(
        meta.get("position_detection_count")
        or meta.get("supplier_position_detection_count")
        or 0
    )
    if detection_count <= 0:
        return False, "no_position_detections"
    return True, None


__all__ = [
    "ProcessingResultKind",
    "RESULT_KIND_POSITION_ONLY",
    "get_result_kind",
    "requires_product_persistence",
    "validate_position_only_evidence",
]
