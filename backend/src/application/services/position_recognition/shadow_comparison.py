"""Compare canonical shadow outcomes with the operational legacy detector."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.domain.position_label_detection.entities import PositionLabelDetectionStatus
from src.domain.position_recognition import (
    CanonicalPositionValidationResult,
    CanonicalPositionValidationStatus,
)


class PositionShadowComparisonOutcome(str, Enum):
    MATCH = "MATCH"
    DIVERGENCE = "DIVERGENCE"
    NOT_EVALUATED = "NOT_EVALUATED"


@dataclass(frozen=True)
class PositionShadowComparison:
    outcome: PositionShadowComparisonOutcome
    reason: str
    canonical_status: str
    legacy_status: str
    resolution_status: str

    def to_metadata(self) -> dict[str, str]:
        return {
            "outcome": self.outcome.value,
            "reason": self.reason,
            "canonical_status": self.canonical_status,
            "legacy_status": self.legacy_status,
            "resolution_status": self.resolution_status,
            "source": "CODE_SCAN",
            "profile": "DINAMIC",
        }


_LEGACY_ACCEPTED = frozenset(
    {
        PositionLabelDetectionStatus.VALID,
        PositionLabelDetectionStatus.LEGACY_UNSIGNED_REQUIRES_REVIEW,
    }
)
_LEGACY_RESOLUTION_OUTCOMES = frozenset(
    {
        PositionLabelDetectionStatus.LABEL_NOT_FOUND,
        PositionLabelDetectionStatus.LABEL_INVALIDATED,
        PositionLabelDetectionStatus.CLIENT_MISMATCH,
    }
)


def compare_position_shadow(
    canonical: CanonicalPositionValidationResult,
    legacy_status: PositionLabelDetectionStatus,
) -> PositionShadowComparison:
    if canonical.status is CanonicalPositionValidationStatus.VALID_PENDING_RESOLUTION:
        if legacy_status in _LEGACY_RESOLUTION_OUTCOMES:
            outcome = PositionShadowComparisonOutcome.NOT_EVALUATED
            reason = "CANONICAL_RESOLUTION_NOT_EVALUATED"
        elif legacy_status in _LEGACY_ACCEPTED:
            outcome = PositionShadowComparisonOutcome.MATCH
            reason = "STRUCTURAL_ACCEPTANCE_MATCH"
        else:
            outcome = PositionShadowComparisonOutcome.DIVERGENCE
            reason = "CANONICAL_STRUCTURAL_ACCEPTS_LEGACY_REJECTS"
        return PositionShadowComparison(
            outcome=outcome,
            reason=reason,
            canonical_status=canonical.status.value,
            legacy_status=legacy_status.value,
            resolution_status=canonical.resolution_status.value,
        )

    canonical_accepted = canonical.operationally_accepted
    legacy_accepted = legacy_status in _LEGACY_ACCEPTED
    if canonical_accepted == legacy_accepted:
        outcome = PositionShadowComparisonOutcome.MATCH
        reason = "ACCEPTANCE_MATCH" if canonical_accepted else "REJECTION_MATCH"
    else:
        outcome = PositionShadowComparisonOutcome.DIVERGENCE
        reason = (
            "CANONICAL_ACCEPTS_LEGACY_REJECTS"
            if canonical_accepted
            else "LEGACY_ACCEPTS_CANONICAL_REJECTS"
        )
    return PositionShadowComparison(
        outcome=outcome,
        reason=reason,
        canonical_status=canonical.status.value,
        legacy_status=legacy_status.value,
        resolution_status=canonical.resolution_status.value,
    )


def record_position_shadow_metric(comparison: PositionShadowComparison) -> None:
    from src.observability.metrics.registry import get_metrics_registry

    get_metrics_registry().inc(
        "position_validation_shadow_comparison_total",
        "Canonical versus legacy position validation shadow comparison",
        {
            "component": "CODE_SCAN",
            "mode": comparison.outcome.value,
            "reason": comparison.reason,
        },
    )
