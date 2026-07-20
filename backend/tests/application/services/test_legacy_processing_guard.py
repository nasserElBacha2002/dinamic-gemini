"""Phase 8 — block new LEGACY_LLM configuration and process overrides."""

from __future__ import annotations

import pytest

from src.application.errors import LegacyProcessingModeNotAllowedError
from src.application.services import legacy_processing_guard as guard
from src.application.services.legacy_processing_guard import (
    LEGACY_PROCESSING_MODE_NOT_ALLOWED_FOR_NEW_CONFIGURATION,
    is_legacy_identification_mode,
    reject_legacy_mode_for_new_configuration,
    reject_legacy_mode_for_new_job,
)
from src.domain.aisle_identification.modes import AisleIdentificationMode


@pytest.fixture(autouse=True)
def _reset_metrics():
    guard.legacy_mode_jobs_blocked_total = 0
    guard.legacy_mode_config_writes_blocked_total = 0
    yield
    guard.legacy_mode_jobs_blocked_total = 0
    guard.legacy_mode_config_writes_blocked_total = 0


def test_is_legacy_identification_mode() -> None:
    assert is_legacy_identification_mode(AisleIdentificationMode.LEGACY_LLM) is True
    assert is_legacy_identification_mode("LEGACY_LLM_TEMPORARY") is True
    assert is_legacy_identification_mode("INTERNAL_OCR") is False
    assert is_legacy_identification_mode(None) is False


def test_reject_legacy_config_allows_clear_and_modern_modes() -> None:
    reject_legacy_mode_for_new_configuration(None)
    reject_legacy_mode_for_new_configuration(AisleIdentificationMode.INTERNAL_OCR)
    reject_legacy_mode_for_new_configuration("CODE_SCAN")


def test_reject_legacy_config_blocks_legacy_llm() -> None:
    with pytest.raises(LegacyProcessingModeNotAllowedError) as exc:
        reject_legacy_mode_for_new_configuration("LEGACY_LLM", context="client")
    assert exc.value.code == LEGACY_PROCESSING_MODE_NOT_ALLOWED_FOR_NEW_CONFIGURATION
    assert guard.legacy_mode_config_writes_blocked_total == 1


def test_reject_legacy_job_override_blocks_explicit_legacy() -> None:
    with pytest.raises(LegacyProcessingModeNotAllowedError):
        reject_legacy_mode_for_new_job(AisleIdentificationMode.LEGACY_LLM)
    assert guard.legacy_mode_jobs_blocked_total == 1


def test_reject_legacy_job_allows_inherit_none() -> None:
    reject_legacy_mode_for_new_job(None)
    assert guard.legacy_mode_jobs_blocked_total == 0
