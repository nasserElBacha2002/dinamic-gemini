"""Shared LLM schema version contracts (no adapter-local string invention)."""

from __future__ import annotations

from enum import StrEnum


class LlmSchemaVersion(StrEnum):
    """Schema versions accepted by LLM executors / external fallback."""

    GLOBAL_V21 = "v2.1"
    EXTERNAL_FALLBACK_V1 = "external_fallback_v1"


def is_external_fallback_schema(schema_version: str | None) -> bool:
    return (schema_version or "").strip() == LlmSchemaVersion.EXTERNAL_FALLBACK_V1


def is_global_v21_schema(schema_version: str | None) -> bool:
    raw = (schema_version or "").strip()
    return raw == LlmSchemaVersion.GLOBAL_V21 or raw in {"v21", "2.1"}


__all__ = [
    "LlmSchemaVersion",
    "is_external_fallback_schema",
    "is_global_v21_schema",
]
