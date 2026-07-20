"""Unit tests for persisted-value coercion helpers in aisle_identification.modes (Phase 1).

Historical null/blank values are lenient (map to a safe default); non-empty unknown values are
a data-integrity problem and must raise ``InvalidPersistedIdentificationModeError`` rather than
being silently coerced.
"""

from __future__ import annotations

import pytest

from src.domain.aisle_identification.modes import (
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
    AisleIdentificationModeSource,
    InvalidPersistedIdentificationModeError,
    historical_job_execution_strategy,
    historical_job_identification_mode,
    historical_job_identification_mode_source,
    optional_config_identification_mode,
)


@pytest.mark.parametrize("value", [None, "", "   "])
def test_historical_job_identification_mode_null_or_blank_defaults_to_legacy_llm(
    value: str | None,
) -> None:
    assert historical_job_identification_mode(value) == AisleIdentificationMode.LEGACY_LLM


def test_historical_job_identification_mode_valid_value_roundtrips() -> None:
    assert historical_job_identification_mode("code_scan") == AisleIdentificationMode.CODE_SCAN
    assert (
        historical_job_identification_mode(AisleIdentificationMode.INTERNAL_OCR)
        == AisleIdentificationMode.INTERNAL_OCR
    )


def test_historical_job_identification_mode_invalid_non_empty_raises() -> None:
    with pytest.raises(InvalidPersistedIdentificationModeError):
        historical_job_identification_mode("AUTO")


@pytest.mark.parametrize("value", [None, "", "  "])
def test_historical_job_identification_mode_source_null_or_blank_defaults_to_legacy_migration(
    value: str | None,
) -> None:
    assert (
        historical_job_identification_mode_source(value)
        == AisleIdentificationModeSource.LEGACY_MIGRATION
    )


def test_historical_job_identification_mode_source_invalid_non_empty_raises() -> None:
    with pytest.raises(InvalidPersistedIdentificationModeError):
        historical_job_identification_mode_source("UNKNOWN_SOURCE")


@pytest.mark.parametrize("value", [None, "", "  "])
def test_historical_job_execution_strategy_null_or_blank_defaults_to_legacy_llm(
    value: str | None,
) -> None:
    assert (
        historical_job_execution_strategy(value) == AisleIdentificationExecutionStrategy.LEGACY_LLM
    )


def test_historical_job_execution_strategy_invalid_non_empty_raises() -> None:
    with pytest.raises(InvalidPersistedIdentificationModeError):
        historical_job_execution_strategy("SOMETHING_ELSE")


@pytest.mark.parametrize("value", [None, "", "  "])
def test_optional_config_identification_mode_null_or_blank_means_inherit(
    value: str | None,
) -> None:
    assert optional_config_identification_mode(value) is None


def test_optional_config_identification_mode_valid_value_roundtrips() -> None:
    assert (
        optional_config_identification_mode("legacy_llm") == AisleIdentificationMode.LEGACY_LLM
    )


def test_optional_config_identification_mode_invalid_non_empty_raises() -> None:
    with pytest.raises(InvalidPersistedIdentificationModeError):
        optional_config_identification_mode("NOT_A_MODE")
