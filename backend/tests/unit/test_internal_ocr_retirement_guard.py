"""Guard: INTERNAL_OCR blocked for new productive jobs/configs."""

from __future__ import annotations

import pytest

from src.application.errors import LegacyProcessingModeNotAllowedError
from src.application.services.legacy_processing_guard import (
    is_retired_internal_ocr_mode,
    reject_legacy_effective_mode_for_new_job,
    reject_legacy_mode_for_new_configuration,
)
from src.domain.aisle_identification.modes import (
    AisleIdentificationMode,
    AisleIdentificationModeSource,
)
from src.domain.aisle_identification.resolver import AisleIdentificationModeResolution


def test_internal_ocr_is_retired_mode() -> None:
    assert is_retired_internal_ocr_mode(AisleIdentificationMode.INTERNAL_OCR)
    assert not is_retired_internal_ocr_mode(AisleIdentificationMode.CODE_SCAN)


def test_reject_internal_ocr_configuration() -> None:
    with pytest.raises(LegacyProcessingModeNotAllowedError):
        reject_legacy_mode_for_new_configuration(
            AisleIdentificationMode.INTERNAL_OCR, context="client"
        )


def test_reject_internal_ocr_effective_job() -> None:
    resolution = AisleIdentificationModeResolution(
        effective_mode=AisleIdentificationMode.INTERNAL_OCR,
        source=AisleIdentificationModeSource.CLIENT,
    )
    with pytest.raises(LegacyProcessingModeNotAllowedError):
        reject_legacy_effective_mode_for_new_job(resolution)
