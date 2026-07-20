"""CODE_SCAN / INTERNAL_OCR feature-flag execution strategy resolution."""

from __future__ import annotations

import pytest

from src.application.errors import StrategyDisabledError
from src.application.services.aisle_identification_execution import (
    resolve_execution_strategy,
    resolve_execution_strategy_decision,
)
from src.domain.aisle_identification.modes import (
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
)


def test_code_scan_flag_off_raises() -> None:
    with pytest.raises(StrategyDisabledError, match="CODE_SCAN_PROCESSING_ENABLED=false"):
        resolve_execution_strategy(
            effective_mode=AisleIdentificationMode.CODE_SCAN,
            pipeline_enabled=True,
            code_scan_processing_enabled=False,
        )


def test_code_scan_flag_on_selects_code_scan() -> None:
    assert (
        resolve_execution_strategy(
            effective_mode=AisleIdentificationMode.CODE_SCAN,
            pipeline_enabled=True,
            code_scan_processing_enabled=True,
        )
        is AisleIdentificationExecutionStrategy.CODE_SCAN
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


def test_legacy_mode_stays_legacy() -> None:
    assert (
        resolve_execution_strategy(
            effective_mode=AisleIdentificationMode.LEGACY_LLM,
            pipeline_enabled=True,
            code_scan_processing_enabled=True,
            internal_ocr_processing_enabled=True,
        )
        is AisleIdentificationExecutionStrategy.LEGACY_LLM
    )


def test_decision_reason_when_enabled() -> None:
    decision = resolve_execution_strategy_decision(
        effective_mode=AisleIdentificationMode.CODE_SCAN,
        pipeline_enabled=True,
        code_scan_processing_enabled=True,
    )
    assert decision.reason == "CODE_SCAN_PROCESSING_ENABLED_TRUE"
