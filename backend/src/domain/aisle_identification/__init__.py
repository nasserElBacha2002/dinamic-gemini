"""Aisle identification mode — Phase 1 (config + job snapshot; no strategy switch yet)."""

from src.domain.aisle_identification.modes import (
    CONFIGURATION_SNAPSHOT_VERSION,
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
    AisleIdentificationModeSource,
    InvalidPersistedIdentificationModeError,
    historical_job_execution_strategy,
    historical_job_identification_mode,
    historical_job_identification_mode_source,
    optional_config_identification_mode,
    parse_execution_strategy,
    parse_identification_mode,
    parse_identification_mode_source,
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
    "InvalidPersistedIdentificationModeError",
    "historical_job_execution_strategy",
    "historical_job_identification_mode",
    "historical_job_identification_mode_source",
    "optional_config_identification_mode",
    "parse_execution_strategy",
    "parse_identification_mode",
    "parse_identification_mode_source",
    "resolve_aisle_identification_mode",
]
