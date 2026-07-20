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
    code_scan_processing_enabled: bool = True,
    internal_ocr_processing_enabled: bool = False,
) -> AisleIdentificationExecutionStrategy:
    """Resolve the actual worker execution path from the effective identification mode.

    ``CODE_SCAN`` is the normal production path for that identification mode (no feature-flag
    gate). The unused ``code_scan_processing_enabled`` kwarg is kept for call-site compatibility
    and ignored.

    ``INTERNAL_OCR`` runs local OCR only when ``internal_ocr_processing_enabled`` is true;
    otherwise it keeps the Phase 1 temporary bridge (``LEGACY_LLM_TEMPORARY`` / ``LEGACY_LLM``).
    ``LEGACY_LLM`` mode always stays on the legacy path.
    """
    _ = code_scan_processing_enabled  # deprecated; CODE_SCAN no longer gated by env
    if effective_mode == AisleIdentificationMode.CODE_SCAN:
        return AisleIdentificationExecutionStrategy.CODE_SCAN
    if (
        effective_mode == AisleIdentificationMode.INTERNAL_OCR
        and internal_ocr_processing_enabled
    ):
        return AisleIdentificationExecutionStrategy.INTERNAL_OCR
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
    """Backward-compatible alias for callers that do not pass code-scan / OCR kwargs.

    Prefer :func:`resolve_execution_strategy`. Selecting ``CODE_SCAN`` resolves to the real
    ``CODE_SCAN`` execution strategy (same as the primary helper). ``INTERNAL_OCR`` stays on
    the temporary legacy bridge unless the OCR flag is passed explicitly.
    """
    return resolve_execution_strategy(
        effective_mode=effective_mode,
        pipeline_enabled=pipeline_enabled,
    )
