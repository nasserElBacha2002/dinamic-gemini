"""Phase 2 — per-image processing domain (state, attempts, strategy contracts).

Legacy productive path remains AISLE_BATCH: one hybrid LLM call for the aisle.
Per-asset rows are logical traceability until Phase 3 runs true per-image strategies.
"""

from __future__ import annotations

from src.domain.image_processing.contracts import (
    ExecutionScope,
    ImageProcessingContext,
    ImageProcessingResult,
    ImageResultStatus,
    ProcessingStrategy,
)
from src.domain.image_processing.job_asset_processing_state import (
    JobAssetProcessingState,
    JobAssetProcessingStatus,
)
from src.domain.image_processing.processing_attempt import (
    ProcessingAttempt,
    ProcessingAttemptStatus,
)

__all__ = [
    "ExecutionScope",
    "ImageProcessingContext",
    "ImageProcessingResult",
    "ImageResultStatus",
    "JobAssetProcessingState",
    "JobAssetProcessingStatus",
    "ProcessingAttempt",
    "ProcessingAttemptStatus",
    "ProcessingStrategy",
]
