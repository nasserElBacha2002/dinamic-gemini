"""Phase 4 execution-strategy resolution + feature flag."""

from __future__ import annotations

import pytest

from src.application.errors import StrategyDisabledError
from src.application.services.aisle_identification_execution import resolve_execution_strategy
from src.domain.aisle_identification.modes import (
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
)


def test_internal_ocr_flag_off_raises() -> None:
    with pytest.raises(StrategyDisabledError, match="INTERNAL_OCR_PROCESSING_ENABLED=false"):
        resolve_execution_strategy(
            effective_mode=AisleIdentificationMode.INTERNAL_OCR,
            pipeline_enabled=True,
            internal_ocr_processing_enabled=False,
        )


def test_internal_ocr_flag_on_selects_internal_ocr() -> None:
    assert (
        resolve_execution_strategy(
            effective_mode=AisleIdentificationMode.INTERNAL_OCR,
            pipeline_enabled=True,
            internal_ocr_processing_enabled=True,
        )
        is AisleIdentificationExecutionStrategy.INTERNAL_OCR
    )


def test_internal_ocr_flag_on_without_pipeline_still_selects_ocr() -> None:
    # Real OCR path is gated by the OCR flag, not the Phase 1 pipeline bridge flag.
    assert (
        resolve_execution_strategy(
            effective_mode=AisleIdentificationMode.INTERNAL_OCR,
            pipeline_enabled=False,
            internal_ocr_processing_enabled=True,
        )
        is AisleIdentificationExecutionStrategy.INTERNAL_OCR
    )
