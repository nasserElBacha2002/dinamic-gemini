"""Legacy LLM strategy — wraps aisle-batch hybrid pipeline (Phase 2).

Physical execution remains AISLE_BATCH. Logical per-asset results are synthesized
after the batch from coverage (evidence / positions), not from separate LLM calls.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from src.domain.aisle_identification.modes import AisleIdentificationMode
from src.domain.assets.entities import SourceAsset
from src.domain.image_processing.contracts import (
    ExecutionScope,
    ImageProcessingContext,
    ImageProcessingResult,
    ImageResultStatus,
)
from src.domain.jobs.entities import Job

logger = logging.getLogger(__name__)

STRATEGY_KEY = "LEGACY_LLM"


@dataclass(frozen=True)
class LegacyBatchOutcome:
    """Result of the existing aisle-batch pipeline + finalization."""

    ok: bool
    report: dict[str, Any] | None = None
    pipeline_result: Any = None
    report_path: str | None = None
    cancelled: bool = False
    #: True when the batch lease could not be acquired (another worker holds it); the legacy
    #: provider was never invoked in this call.
    skipped_busy: bool = False
    error_message: str | None = None
    #: asset_id → whether a position/evidence was linked for this job
    assets_with_result: frozenset[str] = frozenset()


LegacyBatchRunner = Callable[[], LegacyBatchOutcome]


class LegacyLlmProcessingStrategy:
    """Encapsulates current hybrid aisle processing without changing prompts/providers.

    Stateless with respect to the physical runner: ``batch_runner`` is passed per call
    (never stored on ``self``) so one shared instance is safe across concurrent jobs/workers.
    """

    strategy_key = STRATEGY_KEY

    def process(self, context: ImageProcessingContext) -> ImageProcessingResult:
        """Single-asset entry (Phase 3+). Phase 2 aisle path uses ``process_aisle_batch``."""
        return ImageProcessingResult(
            job_id=context.job_id,
            asset_id=context.asset_id,
            status=ImageResultStatus.PENDING_MANUAL_REVIEW,
            processing_mode=context.identification_mode.value
            if isinstance(context.identification_mode, AisleIdentificationMode)
            else str(context.identification_mode),
            resolved_by=STRATEGY_KEY,
            provider_name=context.provider_name,
            model_name=context.model_name,
            execution_scope=ExecutionScope.AISLE_BATCH,
            logical_asset_attempt=True,
            warnings=[
                "Phase 2: per-asset process() is bookkeeping-only; "
                "physical LLM execution is AISLE_BATCH via process_aisle_batch."
            ],
        )

    def process_aisle_batch(
        self,
        *,
        job: Job,
        assets: Sequence[SourceAsset],
        batch_runner: LegacyBatchRunner,
    ) -> LegacyBatchOutcome:
        logger.info(
            "legacy_llm.aisle_batch_start job_id=%s asset_count=%s "
            "identification_mode=%s execution_strategy=%s execution_scope=%s",
            job.id,
            len(assets),
            job.identification_mode.value,
            job.execution_strategy.value,
            ExecutionScope.AISLE_BATCH.value,
        )
        outcome = batch_runner()
        logger.info(
            "legacy_llm.aisle_batch_done job_id=%s ok=%s cancelled=%s "
            "assets_with_result=%s",
            job.id,
            outcome.ok,
            outcome.cancelled,
            len(outcome.assets_with_result),
        )
        return outcome
