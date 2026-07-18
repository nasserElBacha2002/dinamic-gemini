"""Phase 1 helpers: resolve execution strategy label for aisle identification jobs."""

from __future__ import annotations

from src.domain.aisle_identification.modes import (
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
)


def resolve_execution_strategy(
    *,
    effective_mode: AisleIdentificationMode,
    pipeline_enabled: bool,
    code_scan_processing_enabled: bool = False,
) -> AisleIdentificationExecutionStrategy:
    """Resolve the actual worker execution path from the effective identification mode.

    Phase 3: when ``code_scan_processing_enabled`` is on and the effective mode is
    ``CODE_SCAN``, run the deterministic per-image code scan strategy. Otherwise the run
    stays on the legacy LLM pipeline: labelled ``LEGACY_LLM_TEMPORARY`` when the pipeline
    flag is on for a non-legacy mode (operators know barcode/OCR is not the active path),
    else ``LEGACY_LLM``.
    """
    if (
        code_scan_processing_enabled
        and effective_mode == AisleIdentificationMode.CODE_SCAN
    ):
        return AisleIdentificationExecutionStrategy.CODE_SCAN
    if (
        pipeline_enabled
        and effective_mode != AisleIdentificationMode.LEGACY_LLM
    ):
        return AisleIdentificationExecutionStrategy.LEGACY_LLM_TEMPORARY
    return AisleIdentificationExecutionStrategy.LEGACY_LLM


def phase1_execution_strategy(
    *,
    effective_mode: AisleIdentificationMode,
    pipeline_enabled: bool,
) -> AisleIdentificationExecutionStrategy:
    """Backward-compatible alias (pre-Phase-3). Never selects CODE_SCAN.

    Retained so existing Phase 1 call sites and tests keep working; new call sites should
    use :func:`resolve_execution_strategy` and pass ``code_scan_processing_enabled``.
    """
    return resolve_execution_strategy(
        effective_mode=effective_mode,
        pipeline_enabled=pipeline_enabled,
        code_scan_processing_enabled=False,
    )
