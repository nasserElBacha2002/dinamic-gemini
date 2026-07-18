"""Typed aisle identification mode values (independent of inventory production/test)."""

from __future__ import annotations

from enum import Enum


CONFIGURATION_SNAPSHOT_VERSION = 1


class AisleIdentificationMode(str, Enum):
    """How an aisle should be identified when processed.

    Distinct from ``InventoryProcessingMode`` (production | test).
    """

    CODE_SCAN = "CODE_SCAN"
    INTERNAL_OCR = "INTERNAL_OCR"
    LEGACY_LLM = "LEGACY_LLM"


class AisleIdentificationModeSource(str, Enum):
    """Where the effective identification mode was resolved from."""

    REQUEST = "REQUEST"
    AISLE = "AISLE"
    INVENTORY = "INVENTORY"
    CLIENT = "CLIENT"
    SYSTEM_DEFAULT = "SYSTEM_DEFAULT"
    LEGACY_MIGRATION = "LEGACY_MIGRATION"


class AisleIdentificationExecutionStrategy(str, Enum):
    """Actual execution path used by the worker (Phase 1: always legacy LLM)."""

    LEGACY_LLM = "LEGACY_LLM"
    LEGACY_LLM_TEMPORARY = "LEGACY_LLM_TEMPORARY"


def parse_identification_mode(value: str | AisleIdentificationMode) -> AisleIdentificationMode:
    """Parse and validate a mode string; raise ValueError for unknown values."""
    if isinstance(value, AisleIdentificationMode):
        return value
    raw = (value or "").strip()
    if not raw:
        raise ValueError("identification_mode must not be empty")
    try:
        return AisleIdentificationMode(raw.upper())
    except ValueError as exc:
        allowed = ", ".join(m.value for m in AisleIdentificationMode)
        raise ValueError(
            f"Invalid identification_mode {value!r}; expected one of: {allowed}"
        ) from exc


def coerce_identification_mode(
    value: str | AisleIdentificationMode | None,
    *,
    default: AisleIdentificationMode = AisleIdentificationMode.LEGACY_LLM,
) -> AisleIdentificationMode:
    """Coerce DB/API nulls and blanks to ``default`` (historical-job safe)."""
    if value is None:
        return default
    if isinstance(value, AisleIdentificationMode):
        return value
    raw = str(value).strip()
    if not raw:
        return default
    try:
        return AisleIdentificationMode(raw.upper())
    except ValueError:
        return default


def coerce_identification_mode_source(
    value: str | AisleIdentificationModeSource | None,
    *,
    default: AisleIdentificationModeSource = AisleIdentificationModeSource.LEGACY_MIGRATION,
) -> AisleIdentificationModeSource:
    """Coerce null/blank/unknown source strings for historical rows."""
    if value is None:
        return default
    if isinstance(value, AisleIdentificationModeSource):
        return value
    raw = str(value).strip()
    if not raw:
        return default
    try:
        return AisleIdentificationModeSource(raw.upper())
    except ValueError:
        return default
