"""Phase 8 — block new LEGACY_LLM configuration and effective modes."""

from __future__ import annotations

import pytest

from src.application.errors import LegacyProcessingModeNotAllowedError
from src.application.services import legacy_processing_metrics as metrics
from src.application.services.legacy_processing_guard import (
    HISTORICAL_LEGACY_RETRY_ALLOWED,
    LEGACY_PROCESSING_MODE_NOT_ALLOWED_FOR_NEW_CONFIGURATION,
    is_legacy_identification_mode,
    note_historical_legacy_retry_created,
    reject_legacy_effective_mode_for_new_job,
    reject_legacy_mode_for_new_configuration,
    reject_legacy_mode_for_new_job,
)
from src.domain.aisle_identification.modes import (
    AisleIdentificationMode,
    AisleIdentificationModeSource,
)
from src.domain.aisle_identification.resolver import (
    AisleIdentificationModeResolution,
    resolve_aisle_identification_mode,
)


@pytest.fixture(autouse=True)
def _reset_metrics():
    metrics.reset_local_metrics_for_tests()
    yield
    metrics.reset_local_metrics_for_tests()


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
    assert metrics.local_metrics_snapshot()["legacy_mode_config_writes_blocked_total"] == 1


def test_reject_legacy_job_override_blocks_explicit_legacy() -> None:
    with pytest.raises(LegacyProcessingModeNotAllowedError):
        reject_legacy_mode_for_new_job(AisleIdentificationMode.LEGACY_LLM)
    assert metrics.local_metrics_snapshot()["legacy_mode_jobs_blocked_total"] == 1


def test_reject_legacy_job_allows_inherit_none() -> None:
    reject_legacy_mode_for_new_job(None)
    assert metrics.local_metrics_snapshot()["legacy_mode_jobs_blocked_total"] == 0


@pytest.mark.parametrize(
    ("kwargs", "source"),
    [
        ({"aisle_mode": AisleIdentificationMode.LEGACY_LLM}, AisleIdentificationModeSource.AISLE),
        (
            {"inventory_mode": AisleIdentificationMode.LEGACY_LLM},
            AisleIdentificationModeSource.INVENTORY,
        ),
        (
            {"client_mode": AisleIdentificationMode.LEGACY_LLM},
            AisleIdentificationModeSource.CLIENT,
        ),
    ],
)
def test_effective_legacy_blocked_from_inheritance(kwargs, source) -> None:
    resolution = resolve_aisle_identification_mode(**kwargs)
    assert resolution.effective_mode is AisleIdentificationMode.LEGACY_LLM
    assert resolution.source is source
    with pytest.raises(LegacyProcessingModeNotAllowedError):
        reject_legacy_effective_mode_for_new_job(resolution)
    assert metrics.local_metrics_snapshot()["legacy_mode_jobs_blocked_total"] == 1


def test_effective_legacy_blocked_from_system_default_when_forced() -> None:
    """If effective mode is LEGACY (e.g. historical resolver), new jobs are blocked."""
    resolution = AisleIdentificationModeResolution(
        effective_mode=AisleIdentificationMode.LEGACY_LLM,
        source=AisleIdentificationModeSource.SYSTEM_DEFAULT,
    )
    with pytest.raises(LegacyProcessingModeNotAllowedError):
        reject_legacy_effective_mode_for_new_job(resolution)


def test_modern_override_replaces_legacy_inheritance() -> None:
    resolution = resolve_aisle_identification_mode(
        request_mode=AisleIdentificationMode.INTERNAL_OCR,
        aisle_mode=AisleIdentificationMode.LEGACY_LLM,
        inventory_mode=AisleIdentificationMode.LEGACY_LLM,
        client_mode=AisleIdentificationMode.LEGACY_LLM,
    )
    assert resolution.effective_mode is AisleIdentificationMode.INTERNAL_OCR
    reject_legacy_effective_mode_for_new_job(
        resolution,
        requested_mode=AisleIdentificationMode.INTERNAL_OCR,
    )
    assert metrics.local_metrics_snapshot()["legacy_mode_jobs_blocked_total"] == 0


def test_historical_retry_policy_allows_residual_metric() -> None:
    assert HISTORICAL_LEGACY_RETRY_ALLOWED is True
    note_historical_legacy_retry_created(
        identification_mode=AisleIdentificationMode.LEGACY_LLM,
        identification_mode_source=AisleIdentificationModeSource.SYSTEM_DEFAULT,
    )
    assert (
        metrics.local_metrics_snapshot()["legacy_mode_jobs_created_residual_total"] == 1
    )
