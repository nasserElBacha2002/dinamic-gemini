"""Resolve Phase 2+ processing strategy from the immutable job snapshot."""

from __future__ import annotations

import logging

from src.domain.aisle_identification.modes import (
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
)
from src.domain.jobs.entities import Job

logger = logging.getLogger(__name__)

STRATEGY_LEGACY_LLM = "LEGACY_LLM"
STRATEGY_CODE_SCAN = "CODE_SCAN"
STRATEGY_INTERNAL_OCR = "INTERNAL_OCR"


class ProcessingStrategyResolver:
    """Central selector.

    ``CODE_SCAN`` / ``INTERNAL_OCR`` jobs (by immutable ``execution_strategy`` or
    ``identification_mode`` when that mode is the real path) use per-image strategies.
    All other modes stay on LegacyLlm.
    """

    def resolve_strategy_key(
        self,
        job: Job,
        *,
        pipeline_enabled: bool,
        orchestrator_enabled: bool,
        code_scan_processing_enabled: bool = True,
        internal_ocr_processing_enabled: bool = False,
    ) -> str:
        _ = code_scan_processing_enabled  # deprecated; CODE_SCAN is no longer env-gated
        configured = job.identification_mode
        actual = job.execution_strategy
        if (
            actual == AisleIdentificationExecutionStrategy.CODE_SCAN
            or configured == AisleIdentificationMode.CODE_SCAN
        ):
            selected = STRATEGY_CODE_SCAN
        elif (
            actual == AisleIdentificationExecutionStrategy.INTERNAL_OCR
            or (
                configured == AisleIdentificationMode.INTERNAL_OCR
                and internal_ocr_processing_enabled
            )
        ):
            selected = STRATEGY_INTERNAL_OCR
        else:
            selected = STRATEGY_LEGACY_LLM
        logger.info(
            "image_processing.strategy_resolved job_id=%s configured_identification_mode=%s "
            "selected_strategy=%s actual_execution_strategy=%s "
            "aisle_identification_pipeline_enabled=%s image_processing_orchestrator_enabled=%s "
            "internal_ocr_processing_enabled=%s",
            job.id,
            configured.value if isinstance(configured, AisleIdentificationMode) else configured,
            selected,
            actual.value
            if isinstance(actual, AisleIdentificationExecutionStrategy)
            else actual,
            pipeline_enabled,
            orchestrator_enabled,
            internal_ocr_processing_enabled,
        )
        return selected
