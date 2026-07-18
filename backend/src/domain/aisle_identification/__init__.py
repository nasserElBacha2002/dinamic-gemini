"""Aisle identification mode — Phase 1 (config + job snapshot; no strategy switch yet)."""

from src.domain.aisle_identification.modes import (
    CONFIGURATION_SNAPSHOT_VERSION,
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
    AisleIdentificationModeSource,
    coerce_identification_mode,
    coerce_identification_mode_source,
    parse_identification_mode,
)
from src.domain.aisle_identification.resolver import (
    AisleIdentificationModeResolution,
    resolve_aisle_identification_mode,
)

__all__ = [
    "CONFIGURATION_SNAPSHOT_VERSION",
    "AisleIdentificationExecutionStrategy",
    "AisleIdentificationMode",
    "AisleIdentificationModeResolution",
    "AisleIdentificationModeSource",
    "coerce_identification_mode",
    "coerce_identification_mode_source",
    "parse_identification_mode",
    "resolve_aisle_identification_mode",
]
