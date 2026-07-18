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


class ProcessingStrategyResolver:
    """Central selector — Phase 2 always returns LegacyLlm for all modes."""

    def resolve_strategy_key(
        self,
        job: Job,
        *,
        pipeline_enabled: bool,
        orchestrator_enabled: bool,
    ) -> str:
        configured = job.identification_mode
        selected = STRATEGY_LEGACY_LLM
        actual = job.execution_strategy
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
