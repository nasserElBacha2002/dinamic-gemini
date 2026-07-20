"""Typed aisle identification mode values (independent of inventory production/test)."""

from __future__ import annotations

import logging
from enum import Enum

logger = logging.getLogger(__name__)

CONFIGURATION_SNAPSHOT_VERSION = 1


class InvalidPersistedIdentificationModeError(Exception):
    """Non-empty persisted identification field has an unknown value (not historical null)."""


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
    """Actual execution path used by the worker.

    Phase 1/2: always legacy LLM (``LEGACY_LLM`` / ``LEGACY_LLM_TEMPORARY``).
    Phase 3: ``CODE_SCAN`` for deterministic per-image QR/barcode internal-code reading.
    Phase 4: ``INTERNAL_OCR`` for local Tesseract OCR when the feature flag is enabled.
    """

    LEGACY_LLM = "LEGACY_LLM"
    LEGACY_LLM_TEMPORARY = "LEGACY_LLM_TEMPORARY"
    CODE_SCAN = "CODE_SCAN"
    INTERNAL_OCR = "INTERNAL_OCR"


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


def parse_identification_mode_source(
    value: str | AisleIdentificationModeSource,
) -> AisleIdentificationModeSource:
    if isinstance(value, AisleIdentificationModeSource):
        return value
    raw = (value or "").strip()
    if not raw:
        raise ValueError("identification_mode_source must not be empty")
    try:
        return AisleIdentificationModeSource(raw.upper())
    except ValueError as exc:
        allowed = ", ".join(s.value for s in AisleIdentificationModeSource)
        raise ValueError(
            f"Invalid identification_mode_source {value!r}; expected one of: {allowed}"
        ) from exc


def parse_execution_strategy(
    value: str | AisleIdentificationExecutionStrategy,
) -> AisleIdentificationExecutionStrategy:
    if isinstance(value, AisleIdentificationExecutionStrategy):
        return value
    raw = (value or "").strip()
    if not raw:
        raise ValueError("execution_strategy must not be empty")
    try:
        return AisleIdentificationExecutionStrategy(raw.upper())
    except ValueError as exc:
        allowed = ", ".join(s.value for s in AisleIdentificationExecutionStrategy)
        raise ValueError(
            f"Invalid execution_strategy {value!r}; expected one of: {allowed}"
        ) from exc


def historical_job_identification_mode(
    value: str | AisleIdentificationMode | None,
) -> AisleIdentificationMode:
    """Map historical null/blank job mode to LEGACY_LLM; reject non-empty invalid values."""
    if value is None:
        return AisleIdentificationMode.LEGACY_LLM
    if isinstance(value, AisleIdentificationMode):
        return value
    raw = str(value).strip()
    if not raw:
        return AisleIdentificationMode.LEGACY_LLM
    try:
        return AisleIdentificationMode(raw.upper())
    except ValueError as exc:
        logger.error(
            "invalid_persisted_identification_mode field=identification_mode value=%r",
            value,
        )
        raise InvalidPersistedIdentificationModeError(
            f"Invalid persisted identification_mode {value!r}"
        ) from exc


def historical_job_identification_mode_source(
    value: str | AisleIdentificationModeSource | None,
) -> AisleIdentificationModeSource:
    """Map historical null/blank source to LEGACY_MIGRATION; reject non-empty invalid values."""
    if value is None:
        return AisleIdentificationModeSource.LEGACY_MIGRATION
    if isinstance(value, AisleIdentificationModeSource):
        return value
    raw = str(value).strip()
    if not raw:
        return AisleIdentificationModeSource.LEGACY_MIGRATION
    try:
        return AisleIdentificationModeSource(raw.upper())
    except ValueError as exc:
        logger.error(
            "invalid_persisted_identification_mode field=identification_mode_source value=%r",
            value,
        )
        raise InvalidPersistedIdentificationModeError(
            f"Invalid persisted identification_mode_source {value!r}"
        ) from exc


def historical_job_execution_strategy(
    value: str | AisleIdentificationExecutionStrategy | None,
) -> AisleIdentificationExecutionStrategy:
    if value is None:
        return AisleIdentificationExecutionStrategy.LEGACY_LLM
    if isinstance(value, AisleIdentificationExecutionStrategy):
        return value
    raw = str(value).strip()
    if not raw:
        return AisleIdentificationExecutionStrategy.LEGACY_LLM
    try:
        return AisleIdentificationExecutionStrategy(raw.upper())
    except ValueError as exc:
        logger.error(
            "invalid_persisted_identification_mode field=execution_strategy value=%r",
            value,
        )
        raise InvalidPersistedIdentificationModeError(
            f"Invalid persisted execution_strategy {value!r}"
        ) from exc


def optional_config_identification_mode(
    value: str | AisleIdentificationMode | None,
) -> AisleIdentificationMode | None:
    """Nullable config column: null/blank → None (inherit); non-empty invalid → error."""
    if value is None:
        return None
    if isinstance(value, AisleIdentificationMode):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return AisleIdentificationMode(raw.upper())
    except ValueError as exc:
        logger.error(
            "invalid_persisted_identification_mode field=config_identification_mode value=%r",
            value,
        )
        raise InvalidPersistedIdentificationModeError(
            f"Invalid persisted identification_mode {value!r}"
        ) from exc
