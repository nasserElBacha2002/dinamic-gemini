"""Recovery attempt status mapping — Phase 3.4 corrections."""

from __future__ import annotations

import pytest

from src.application.services.finalization_recovery_support import map_recovery_outcome_to_attempt_status
from src.domain.jobs.finalization_recovery import RecoveryAttemptStatus, RecoveryOutcome


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (RecoveryOutcome.RECOVERED, RecoveryAttemptStatus.SUCCEEDED),
        (RecoveryOutcome.ALREADY_COMPLETE, RecoveryAttemptStatus.SUCCEEDED),
        (RecoveryOutcome.ALREADY_OPERATIONAL, RecoveryAttemptStatus.SUCCEEDED),
        (RecoveryOutcome.ALREADY_SUPERSEDED, RecoveryAttemptStatus.SUCCEEDED),
        (RecoveryOutcome.FAILED, RecoveryAttemptStatus.FAILED),
        (RecoveryOutcome.PARTIALLY_RECOVERED, RecoveryAttemptStatus.PARTIAL),
        (RecoveryOutcome.NOT_ELIGIBLE, RecoveryAttemptStatus.REJECTED),
        (RecoveryOutcome.INCONSISTENT, RecoveryAttemptStatus.REJECTED),
        (RecoveryOutcome.CONCURRENCY_CONFLICT, RecoveryAttemptStatus.REJECTED),
        (RecoveryOutcome.VERIFICATION_REQUIRED, RecoveryAttemptStatus.REJECTED),
        (RecoveryOutcome.SOURCE_UNAVAILABLE, RecoveryAttemptStatus.REJECTED),
    ],
)
def test_map_recovery_outcome_to_attempt_status(outcome, expected) -> None:
    assert map_recovery_outcome_to_attempt_status(outcome) == expected
