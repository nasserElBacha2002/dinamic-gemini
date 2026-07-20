"""Resolve aisle identification execution strategy with an auditable reason."""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.aisle_identification.modes import (
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
)


@dataclass(frozen=True)
class ExecutionStrategyDecision:
    """Immutable decision snapshotted at job creation (do not re-resolve on retry)."""

    requested_mode: AisleIdentificationMode
    strategy: AisleIdentificationExecutionStrategy
    reason: str
    code_scan_processing_enabled: bool
    internal_ocr_processing_enabled: bool
    pipeline_enabled: bool


def resolve_execution_strategy_decision(
    *,
    effective_mode: AisleIdentificationMode,
    pipeline_enabled: bool,
    code_scan_processing_enabled: bool = False,
    internal_ocr_processing_enabled: bool = False,
) -> ExecutionStrategyDecision:
    """Resolve the worker path from mode + feature flags.

    ``CODE_SCAN`` / ``INTERNAL_OCR`` only become real execution strategies when their
    respective flags are enabled. Otherwise they fall back to the Phase 1 temporary bridge
    (``LEGACY_LLM_TEMPORARY`` when the aisle-identification pipeline flag is on, else
    ``LEGACY_LLM``).
    """
    if effective_mode == AisleIdentificationMode.CODE_SCAN:
        if code_scan_processing_enabled:
            return ExecutionStrategyDecision(
                requested_mode=effective_mode,
                strategy=AisleIdentificationExecutionStrategy.CODE_SCAN,
                reason="CODE_SCAN_PROCESSING_ENABLED_TRUE",
                code_scan_processing_enabled=True,
                internal_ocr_processing_enabled=internal_ocr_processing_enabled,
                pipeline_enabled=pipeline_enabled,
            )
        if pipeline_enabled:
            return ExecutionStrategyDecision(
                requested_mode=effective_mode,
                strategy=AisleIdentificationExecutionStrategy.LEGACY_LLM_TEMPORARY,
                reason="CODE_SCAN_PROCESSING_ENABLED_FALSE",
                code_scan_processing_enabled=False,
                internal_ocr_processing_enabled=internal_ocr_processing_enabled,
                pipeline_enabled=True,
            )
        return ExecutionStrategyDecision(
            requested_mode=effective_mode,
            strategy=AisleIdentificationExecutionStrategy.LEGACY_LLM,
            reason="CODE_SCAN_PROCESSING_ENABLED_FALSE_PIPELINE_OFF",
            code_scan_processing_enabled=False,
            internal_ocr_processing_enabled=internal_ocr_processing_enabled,
            pipeline_enabled=False,
        )

    if effective_mode == AisleIdentificationMode.INTERNAL_OCR:
        if internal_ocr_processing_enabled:
            return ExecutionStrategyDecision(
                requested_mode=effective_mode,
                strategy=AisleIdentificationExecutionStrategy.INTERNAL_OCR,
                reason="INTERNAL_OCR_PROCESSING_ENABLED_TRUE",
                code_scan_processing_enabled=code_scan_processing_enabled,
                internal_ocr_processing_enabled=True,
                pipeline_enabled=pipeline_enabled,
            )
        if pipeline_enabled:
            return ExecutionStrategyDecision(
                requested_mode=effective_mode,
                strategy=AisleIdentificationExecutionStrategy.LEGACY_LLM_TEMPORARY,
                reason="INTERNAL_OCR_PROCESSING_ENABLED_FALSE",
                code_scan_processing_enabled=code_scan_processing_enabled,
                internal_ocr_processing_enabled=False,
                pipeline_enabled=True,
            )
        return ExecutionStrategyDecision(
            requested_mode=effective_mode,
            strategy=AisleIdentificationExecutionStrategy.LEGACY_LLM,
            reason="INTERNAL_OCR_PROCESSING_ENABLED_FALSE_PIPELINE_OFF",
            code_scan_processing_enabled=code_scan_processing_enabled,
            internal_ocr_processing_enabled=False,
            pipeline_enabled=False,
        )

    # LEGACY_LLM (or unknown mapped earlier) always stays on the legacy path.
    return ExecutionStrategyDecision(
        requested_mode=effective_mode,
        strategy=AisleIdentificationExecutionStrategy.LEGACY_LLM,
        reason="LEGACY_LLM_MODE",
        code_scan_processing_enabled=code_scan_processing_enabled,
        internal_ocr_processing_enabled=internal_ocr_processing_enabled,
        pipeline_enabled=pipeline_enabled,
    )


def resolve_execution_strategy(
    *,
    effective_mode: AisleIdentificationMode,
    pipeline_enabled: bool,
    code_scan_processing_enabled: bool = False,
    internal_ocr_processing_enabled: bool = False,
) -> AisleIdentificationExecutionStrategy:
    """Resolve the actual worker execution path from the effective identification mode."""
    return resolve_execution_strategy_decision(
        effective_mode=effective_mode,
        pipeline_enabled=pipeline_enabled,
        code_scan_processing_enabled=code_scan_processing_enabled,
        internal_ocr_processing_enabled=internal_ocr_processing_enabled,
    ).strategy


def phase1_execution_strategy(
    *,
    effective_mode: AisleIdentificationMode,
    pipeline_enabled: bool,
) -> AisleIdentificationExecutionStrategy:
    """Backward-compatible alias (CODE_SCAN / INTERNAL_OCR flags default off)."""
    return resolve_execution_strategy(
        effective_mode=effective_mode,
        pipeline_enabled=pipeline_enabled,
    )


def identification_execution_snapshot_dict(
    decision: ExecutionStrategyDecision,
    *,
    ocr_config: dict | None = None,
    client_rules: dict | None = None,
    configuration_snapshot_version: int,
    external_fallback: dict | None = None,
) -> dict:
    """Build the immutable identification-execution block stored on the job."""
    feature_flags = {
        "code_scan_processing_enabled": decision.code_scan_processing_enabled,
        "internal_ocr_processing_enabled": decision.internal_ocr_processing_enabled,
        "aisle_identification_pipeline_enabled": decision.pipeline_enabled,
    }
    if isinstance(external_fallback, dict):
        feature_flags["external_fallback_per_image_enabled"] = bool(
            external_fallback.get("fallback_enabled")
        )
    return {
        "requested_mode": decision.requested_mode.value,
        "executed_strategy": decision.strategy.value,
        "reason": decision.reason,
        "configuration_source": decision.requested_mode.value,
        "feature_flag_state": feature_flags,
        "snapshot_version": int(configuration_snapshot_version),
        "ocr_config": ocr_config,
        "client_rules": client_rules,
        "external_fallback": external_fallback,
    }
