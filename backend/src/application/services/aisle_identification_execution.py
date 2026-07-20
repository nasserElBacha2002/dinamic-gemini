"""Resolve aisle identification execution strategy with an auditable reason."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.errors import StrategyDisabledError
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

    ``CODE_SCAN`` / ``INTERNAL_OCR`` require their flags enabled. Disabled strategies
    raise ``StrategyDisabledError`` — they must not silently fall back to legacy LLM.
    """
    if effective_mode == AisleIdentificationMode.CODE_SCAN:
        if not code_scan_processing_enabled:
            raise StrategyDisabledError(
                "CODE_SCAN_PROCESSING_ENABLED=false; cannot start CODE_SCAN jobs"
            )
        return ExecutionStrategyDecision(
            requested_mode=effective_mode,
            strategy=AisleIdentificationExecutionStrategy.CODE_SCAN,
            reason="CODE_SCAN_PROCESSING_ENABLED_TRUE",
            code_scan_processing_enabled=True,
            internal_ocr_processing_enabled=internal_ocr_processing_enabled,
            pipeline_enabled=pipeline_enabled,
        )

    if effective_mode == AisleIdentificationMode.INTERNAL_OCR:
        if not internal_ocr_processing_enabled:
            raise StrategyDisabledError(
                "INTERNAL_OCR_PROCESSING_ENABLED=false; cannot start INTERNAL_OCR jobs"
            )
        return ExecutionStrategyDecision(
            requested_mode=effective_mode,
            strategy=AisleIdentificationExecutionStrategy.INTERNAL_OCR,
            reason="INTERNAL_OCR_PROCESSING_ENABLED_TRUE",
            code_scan_processing_enabled=code_scan_processing_enabled,
            internal_ocr_processing_enabled=True,
            pipeline_enabled=pipeline_enabled,
        )

    # LEGACY_LLM remains only for historical retries / explicit residual paths.
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
    supplier_extraction_profile: dict | None = None,
    client_extraction_profiles_enabled: bool = False,
    profile_aware_validation_enabled: bool = False,
    reference_template_annotations_enabled: bool = False,
    profile_snapshotted: bool = False,
    profile_validation_executed: bool = False,
) -> dict:
    """Build the immutable identification-execution block stored on the job."""
    feature_flags = {
        "code_scan_processing_enabled": decision.code_scan_processing_enabled,
        "internal_ocr_processing_enabled": decision.internal_ocr_processing_enabled,
        "aisle_identification_pipeline_enabled": decision.pipeline_enabled,
        "client_extraction_profiles_enabled": bool(client_extraction_profiles_enabled),
        "profile_aware_validation_enabled": bool(profile_aware_validation_enabled),
        "reference_template_annotations_enabled": bool(
            reference_template_annotations_enabled
        ),
        "profile_snapshotted": bool(profile_snapshotted),
        "profile_validation_executed": bool(profile_validation_executed),
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
        "supplier_extraction_profile": supplier_extraction_profile,
    }
