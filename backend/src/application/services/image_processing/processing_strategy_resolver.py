"""Resolve Phase 2 processing strategy from the immutable job snapshot."""

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


class ProcessingStrategyResolver:
    """Central selector.

    Phase 2 always returns LegacyLlm. Phase 3 returns CODE_SCAN when the job was started as
    CODE_SCAN (immutable snapshot) or when the code-scan flag is on and the configured
    identification mode is CODE_SCAN.
    """

    def resolve_strategy_key(
        self,
        job: Job,
        *,
        pipeline_enabled: bool,
        orchestrator_enabled: bool,
        code_scan_processing_enabled: bool = False,
    ) -> str:
        configured = job.identification_mode
        actual = job.execution_strategy
        if actual == AisleIdentificationExecutionStrategy.CODE_SCAN or (
            code_scan_processing_enabled
            and configured == AisleIdentificationMode.CODE_SCAN
        ):
            selected = STRATEGY_CODE_SCAN
        else:
            selected = STRATEGY_LEGACY_LLM
        logger.info(
            "image_processing.strategy_resolved job_id=%s configured_identification_mode=%s "
            "selected_strategy=%s actual_execution_strategy=%s "
            "aisle_identification_pipeline_enabled=%s image_processing_orchestrator_enabled=%s",
            job.id,
            configured.value if isinstance(configured, AisleIdentificationMode) else configured,
            selected,
            actual.value
            if isinstance(actual, AisleIdentificationExecutionStrategy)
            else actual,
            pipeline_enabled,
            orchestrator_enabled,
        )
        return selected
