"""CODE_SCAN is the normal execution path when that identification mode is selected."""

from __future__ import annotations

from src.application.services.aisle_identification_execution import (
    phase1_execution_strategy,
    resolve_execution_strategy,
)
from src.domain.aisle_identification.modes import (
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
)


def test_code_scan_mode_always_selects_code_scan_strategy() -> None:
    assert (
        resolve_execution_strategy(
            effective_mode=AisleIdentificationMode.CODE_SCAN,
            pipeline_enabled=False,
            code_scan_processing_enabled=False,  # ignored
        )
        is AisleIdentificationExecutionStrategy.CODE_SCAN
    )
    assert (
        resolve_execution_strategy(
            effective_mode=AisleIdentificationMode.CODE_SCAN,
            pipeline_enabled=True,
        )
        is AisleIdentificationExecutionStrategy.CODE_SCAN
    )


def test_internal_ocr_still_temporary_when_pipeline_on() -> None:
    assert (
        resolve_execution_strategy(
            effective_mode=AisleIdentificationMode.INTERNAL_OCR,
            pipeline_enabled=True,
        )
        is AisleIdentificationExecutionStrategy.LEGACY_LLM_TEMPORARY
    )


def test_legacy_mode_stays_legacy() -> None:
    assert (
        resolve_execution_strategy(
            effective_mode=AisleIdentificationMode.LEGACY_LLM,
            pipeline_enabled=True,
        )
        is AisleIdentificationExecutionStrategy.LEGACY_LLM
    )


def test_phase1_alias_also_selects_code_scan() -> None:
    assert (
        phase1_execution_strategy(
            effective_mode=AisleIdentificationMode.CODE_SCAN,
            pipeline_enabled=False,
        )
        is AisleIdentificationExecutionStrategy.CODE_SCAN
    )
