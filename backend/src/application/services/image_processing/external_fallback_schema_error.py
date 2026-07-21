"""Safe structured schema-validation diagnostics for external fallback (no payload leakage)."""

from __future__ import annotations

from typing import Any

from src.llm.response_trace import response_trace_metadata

__all__ = [
    "build_external_schema_validation_error",
    "response_trace_metadata",
]


def build_external_schema_validation_error(
    *,
    phase: str,
    reason_code: str,
    field: str | None = None,
    expected_type: str | None = None,
    received_type: str | None = None,
) -> dict[str, Any]:
    """Return a non-sensitive schema error contract for events / additional_fields."""
    return {
        "status": "EXTERNAL_SCHEMA_INVALID",
        "phase": phase,
        "field": field,
        "reason_code": reason_code,
        "expected_type": expected_type,
        "received_type": received_type,
    }
