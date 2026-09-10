"""Shadow evaluation of flexible position policy without changing productive decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.application.services.position_recognition.channel_gates import FlexiblePositionChannel
from src.application.services.position_recognition.validator import (
    CanonicalPositionValidationCommand,
    CanonicalPositionValidator,
    PositionCompatibilityPolicy,
)
from src.domain.position_recognition import CanonicalPositionValidationResult
from src.observability.metrics.instruments import (
    record_position_flexible_divergence,
    record_position_flexible_evaluation,
)


class FlexibleShadowOutcome(str, Enum):
    MATCH_ACCEPT = "MATCH_ACCEPT"
    MATCH_REJECT = "MATCH_REJECT"
    DIVERGENCE_FLEXIBLE_ACCEPTS = "DIVERGENCE_FLEXIBLE_ACCEPTS"
    DIVERGENCE_FLEXIBLE_REJECTS = "DIVERGENCE_FLEXIBLE_REJECTS"


@dataclass(frozen=True)
class FlexibleShadowComparison:
    outcome: FlexibleShadowOutcome
    productive_status: str
    shadow_status: str

    @property
    def diverged(self) -> bool:
        return self.outcome in {
            FlexibleShadowOutcome.DIVERGENCE_FLEXIBLE_ACCEPTS,
            FlexibleShadowOutcome.DIVERGENCE_FLEXIBLE_REJECTS,
        }


@dataclass(frozen=True)
class FlexibleShadowEvaluation:
    """Productive result is always the legacy/current policy outcome."""

    productive: CanonicalPositionValidationResult
    shadow: CanonicalPositionValidationResult | None
    comparison: FlexibleShadowComparison | None


def flexible_shadow_policy(legacy: PositionCompatibilityPolicy) -> PositionCompatibilityPolicy:
    """Flexible shadow snapshot: master flexible on, preexistence off."""
    return PositionCompatibilityPolicy.resolve(
        signature_validation_enabled=legacy.signature_validation_enabled,
        allow_unsigned_legacy=legacy.allow_unsigned_legacy,
        preexistence_required=False,
        flexible_validation_enabled=True,
        signature_policy=legacy.signature_policy,
    )


def compare_flexible_shadow(
    productive: CanonicalPositionValidationResult,
    shadow: CanonicalPositionValidationResult,
) -> FlexibleShadowComparison:
    productive_accepted = productive.operationally_accepted
    shadow_accepted = shadow.operationally_accepted
    if productive_accepted and shadow_accepted:
        outcome = FlexibleShadowOutcome.MATCH_ACCEPT
    elif not productive_accepted and not shadow_accepted:
        outcome = FlexibleShadowOutcome.MATCH_REJECT
    elif shadow_accepted:
        outcome = FlexibleShadowOutcome.DIVERGENCE_FLEXIBLE_ACCEPTS
    else:
        outcome = FlexibleShadowOutcome.DIVERGENCE_FLEXIBLE_REJECTS
    return FlexibleShadowComparison(
        outcome=outcome,
        productive_status=productive.status.value,
        shadow_status=shadow.status.value,
    )


class PositionFlexibleShadowEvaluator:
    """Run flexible policy in shadow; never change productive accept/reject."""

    def __init__(
        self,
        *,
        enabled: bool,
        channel: FlexiblePositionChannel = FlexiblePositionChannel.CODE_SCAN,
    ) -> None:
        self._enabled = bool(enabled)
        self._channel = channel

    def evaluate(
        self,
        validator: CanonicalPositionValidator,
        command: CanonicalPositionValidationCommand,
        *,
        record_operational_metrics: bool = True,
    ) -> FlexibleShadowEvaluation:
        productive = validator.validate(
            command,
            record_operational_metrics=record_operational_metrics,
        )
        if not self._enabled:
            record_position_flexible_evaluation(
                channel=self._channel.value,
                outcome="SHADOW_DISABLED",
            )
            return FlexibleShadowEvaluation(
                productive=productive,
                shadow=None,
                comparison=None,
            )

        shadow_validator = validator.with_policy(flexible_shadow_policy(validator.policy))
        shadow = shadow_validator.validate(
            command,
            record_operational_metrics=False,
        )
        comparison = compare_flexible_shadow(productive, shadow)
        record_position_flexible_evaluation(
            channel=self._channel.value,
            outcome=comparison.outcome.value,
        )
        if comparison.diverged:
            record_position_flexible_divergence(
                channel=self._channel.value,
                outcome=comparison.outcome.value,
            )
        return FlexibleShadowEvaluation(
            productive=productive,
            shadow=shadow,
            comparison=comparison,
        )
