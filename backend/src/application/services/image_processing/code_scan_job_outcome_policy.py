"""Phase 3 corrections — deterministic CODE_SCAN job outcome policy.

Maps the terminal per-asset progress counters of a CODE_SCAN run to a single job-level
outcome. Kept pure (no I/O) so it is trivially unit-testable and auditable: the same counters
always map to the same outcome. The executor uses this to decide job finalization, and — most
importantly — to never report success for a run that left assets stuck in a non-terminal state.
"""

from __future__ import annotations

from enum import Enum

from src.application.ports.image_processing_repositories import AssetProgressCounts


class CodeScanJobOutcome(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


def decide(
    *,
    progress: AssetProgressCounts,
    cancelled: bool,
    infrastructure_error: str | None,
) -> CodeScanJobOutcome:
    """Decide the job-level outcome from terminal per-asset counters.

    Precedence (highest first):
    1. ``cancelled`` → CANCELLED.
    2. ``infrastructure_error`` present → FAILED (a run-level technical failure).
    3. Empty aisle (``total == 0``) → SUCCEEDED (nothing to do is a completed job).
    4. Any asset left PENDING/PROCESSING at the end → FAILED (state inconsistency: the run
       claims to be over but assets never reached a terminal status).
    5. All assets FAILED_TECHNICAL → FAILED.
    6. Some assets FAILED_TECHNICAL but at least one reached a productive terminal status
       (RESOLVED / UNRECOGNIZED / PENDING_MANUAL_REVIEW) → PARTIALLY_COMPLETED.
    7. Otherwise → SUCCEEDED (includes all-UNRECOGNIZED or all-PENDING_MANUAL_REVIEW: the run
       completed deterministically even though no code was resolved).
    """
    if cancelled:
        return CodeScanJobOutcome.CANCELLED
    if infrastructure_error:
        return CodeScanJobOutcome.FAILED

    total = int(progress.total)
    if total == 0:
        return CodeScanJobOutcome.SUCCEEDED

    if int(progress.pending) > 0 or int(progress.processing) > 0:
        return CodeScanJobOutcome.FAILED

    failed = int(progress.failed)
    if failed >= total and failed > 0:
        return CodeScanJobOutcome.FAILED

    productive = (
        int(progress.resolved)
        + int(progress.unrecognized)
        + int(progress.manual_review)
    )
    if failed > 0 and productive > 0:
        return CodeScanJobOutcome.PARTIALLY_COMPLETED

    return CodeScanJobOutcome.SUCCEEDED


__all__ = ["CodeScanJobOutcome", "decide"]
