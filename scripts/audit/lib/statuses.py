"""Tool status vocabulary for the Phase 0 audit runner (schema_version 2)."""

from __future__ import annotations

from enum import Enum


class ToolStatus(str, Enum):
    OK = "OK"
    FINDINGS = "FINDINGS"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    PARSE_ERROR = "PARSE_ERROR"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    NOT_RUN = "NOT_RUN"
    SKIPPED = "SKIPPED"

    # Backward-compatible alias used in older reports / area rollups.
    ERROR = "ERROR"


# Statuses that invalidate the quality gate (tooling broken, not mere findings).
INVALIDATING_STATUSES = frozenset(
    {
        ToolStatus.EXECUTION_ERROR.value,
        ToolStatus.PARSE_ERROR.value,
        ToolStatus.ERROR.value,
        ToolStatus.NOT_AVAILABLE.value,
    }
)

# Intentional omission — gate fails unless explicitly allowed.
OMITTED_STATUSES = frozenset(
    {
        ToolStatus.NOT_RUN.value,
        ToolStatus.SKIPPED.value,
    }
)

SCHEMA_VERSION = 2
PARSER_VERSION = "phase0-2.0.0"


def normalize_legacy_status(status: str) -> str:
    """Map legacy shell/aggregator labels onto schema v2 statuses."""
    s = (status or "").strip().upper()
    if s in {"NOT_INSTALLED"}:
        return ToolStatus.NOT_AVAILABLE.value
    if s in {e.value for e in ToolStatus}:
        return s
    if s == "ERROR":
        return ToolStatus.ERROR.value
    return ToolStatus.PARSE_ERROR.value


def is_invalidating(status: str) -> bool:
    return normalize_legacy_status(status) in INVALIDATING_STATUSES


def is_omitted(status: str) -> bool:
    return normalize_legacy_status(status) in OMITTED_STATUSES
