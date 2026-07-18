"""Phase 1 helpers: resolve execution strategy label for aisle identification jobs."""

from __future__ import annotations

from src.domain.aisle_identification.modes import (
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
)


def phase1_execution_strategy(
    *,
    effective_mode: AisleIdentificationMode,
    pipeline_enabled: bool,
) -> AisleIdentificationExecutionStrategy:
    """Phase 1 always runs the legacy LLM pipeline.

    When the feature flag is on and the configured mode is not LEGACY_LLM, label the run as
    ``LEGACY_LLM_TEMPORARY`` so operators know barcode/OCR strategies are not active yet.
    """
    if (
        pipeline_enabled
        and effective_mode != AisleIdentificationMode.LEGACY_LLM
    ):
        return AisleIdentificationExecutionStrategy.LEGACY_LLM_TEMPORARY
    return AisleIdentificationExecutionStrategy.LEGACY_LLM
