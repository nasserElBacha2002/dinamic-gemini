"""Centralized Phase 4 position transition policy."""

from __future__ import annotations

from enum import Enum

from src.domain.position_reconciliation.entities import PositionTransitionAction

_CLEAR_STATUSES = frozenset(
    {
        "INVALID_SIGNATURE",
        "CLIENT_MISMATCH",
        "LABEL_INVALIDATED",
        "AMBIGUOUS_POSITION_DETECTION",
    }
)

_KEEP_STATUSES = frozenset(
    {
        "NO_LABEL",
        "INVALID_JSON",
        "INVALID_TYPE",
        "FEATURE_DISABLED",
        "DETECTION_FAILED",
        "DETECTION_CONTEXT_INVALID",
        "DECODE_TIMEOUT",
        "PAYLOAD_TOO_LARGE",
        "UNSUPPORTED_VERSION",
        "UNSUPPORTED_LEGACY_PAYLOAD",
        "MISSING_LABEL_ID",
        "MISSING_SIGNATURE",
        "UNKNOWN_KEY",
        "UNKNOWN_KEY_VERSION",
        "LABEL_NOT_FOUND",
        "DUPLICATE",
        "DUPLICATE_POSITION_CODES",
        "SIGNATURE_VALIDATION_SKIPPED",
    }
)

# Resolved unsigned labels (matched to a stored client label) establish position so
# product↔position association works for the common unsigned-label printer path.
# Assignment rows carry LEGACY_UNSIGNED_REQUIRES_REVIEW in warnings for operator review.
_SET_STATUSES = frozenset(
    {
        "VALID",
        "LEGACY_UNSIGNED_REQUIRES_REVIEW",
    }
)


def resolve_position_transition(
    detection_status: str | Enum,
) -> PositionTransitionAction:
    """Return the state transition for a normalized Phase 3 detection status."""

    raw = detection_status.value if isinstance(detection_status, Enum) else detection_status
    status = str(raw).strip().upper()
    if status in _SET_STATUSES:
        return PositionTransitionAction.SET_POSITION
    if status in _CLEAR_STATUSES:
        return PositionTransitionAction.CLEAR_POSITION
    if (
        status in _KEEP_STATUSES
        or status.startswith("UNSUPPORTED_")
        or status.startswith("MISSING_")
    ):
        return PositionTransitionAction.KEEP_POSITION
    return PositionTransitionAction.KEEP_POSITION
