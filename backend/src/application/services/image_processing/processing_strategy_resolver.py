"""Resolve Phase 2+ processing strategy from the immutable job snapshot."""

from __future__ import annotations

import logging

from src.domain.aisle_identification.modes import AisleIdentificationExecutionStrategy
from src.domain.jobs.entities import Job

logger = logging.getLogger(__name__)

STRATEGY_LEGACY_LLM = "LEGACY_LLM"
STRATEGY_CODE_SCAN = "CODE_SCAN"
STRATEGY_INTERNAL_OCR = "INTERNAL_OCR"


class ProcessingStrategyResolver:
    """Central selector — trusts the immutable ``execution_strategy`` snapshotted at job start.

    Feature flags are applied only when creating the job. Workers and retries must not
    re-interpret env flags against ``identification_mode``.
    """

    def resolve_strategy_key(
        self,
        job: Job,
        *,
        pipeline_enabled: bool,
        orchestrator_enabled: bool,
        code_scan_processing_enabled: bool = False,
        internal_ocr_processing_enabled: bool = False,
    ) -> str:
        # Flags are intentionally unused here: the job snapshot already encoded them.
        _ = (
            code_scan_processing_enabled,
            internal_ocr_processing_enabled,
            pipeline_enabled,
            orchestrator_enabled,
        )
        configured = job.identification_mode
        actual = job.execution_strategy
        if actual == AisleIdentificationExecutionStrategy.CODE_SCAN:
            selected = STRATEGY_CODE_SCAN
        elif actual == AisleIdentificationExecutionStrategy.INTERNAL_OCR:
            selected = STRATEGY_INTERNAL_OCR
        else:
            selected = STRATEGY_LEGACY_LLM
        logger.info(
            "image_processing.strategy_resolved job_id=%s configured_identification_mode=%s "
            "selected_strategy=%s actual_execution_strategy=%s",
            job.id,
            getattr(configured, "value", configured),
            selected,
            getattr(actual, "value", actual),
        )
        return selected
