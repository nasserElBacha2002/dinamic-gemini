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
from src.domain.position_recognition import (
    CanonicalPositionValidationResult,
    CanonicalPositionValidationStatus,
)
from src.observability.metrics.instruments import (
    record_position_flexible_divergence,
    record_position_flexible_evaluation,
)

_SIGNATURE_STATUSES = frozenset(
    {
        CanonicalPositionValidationStatus.INVALID_SIGNATURE,
        CanonicalPositionValidationStatus.SIGNATURE_VALIDATION_SKIPPED,
        CanonicalPositionValidationStatus.SIGNATURE_REQUIRED_BY_LEGACY_POLICY,
        CanonicalPositionValidationStatus.SIGNATURE_NOT_ALLOWED_FOR_PROFILE,
    }
)
_PREEXISTENCE_STATUSES = frozenset(
    {
        CanonicalPositionValidationStatus.PREEXISTENCE_REQUIRED_BY_LEGACY_POLICY,
        CanonicalPositionValidationStatus.VALID_UNMATERIALIZED,
        CanonicalPositionValidationStatus.VALID_EXISTING,
        CanonicalPositionValidationStatus.VALID_PENDING_RESOLUTION,
    }
)
_CLASSIFICATION_STATUSES = frozenset(
    {
        CanonicalPositionValidationStatus.AMBIGUOUS_CODE,
        CanonicalPositionValidationStatus.PROFILE_NOT_ALLOWED,
    }
)
_FORMAT_STATUSES = frozenset(
    {
        CanonicalPositionValidationStatus.INVALID_FORMAT,
        CanonicalPositionValidationStatus.FIELD_CONSTRAINT_VIOLATION,
        CanonicalPositionValidationStatus.INVALID_CHECKSUM,
    }
)
_SCOPE_STATUSES = frozenset(
    {
        CanonicalPositionValidationStatus.PROFILE_NOT_ALLOWED,
    }
)


class FlexibleShadowOutcome(str, Enum):
    MATCH_ACCEPT = "MATCH_ACCEPT"
    MATCH_REJECT = "MATCH_REJECT"
    DIVERGENCE_FLEXIBLE_ACCEPTS = "DIVERGENCE_FLEXIBLE_ACCEPTS"
    DIVERGENCE_FLEXIBLE_REJECTS = "DIVERGENCE_FLEXIBLE_REJECTS"


class FlexibleShadowDivergenceCategory(str, Enum):
    SIGNATURE = "SIGNATURE"
    PREEXISTENCE = "PREEXISTENCE"
    CLASSIFICATION = "CLASSIFICATION"
    FORMAT = "FORMAT"
    SCOPE = "SCOPE"
    MATERIALIZATION_POSSIBLE = "MATERIALIZATION_POSSIBLE"
    OTHER = "OTHER"


@dataclass(frozen=True)
class FlexibleShadowComparison:
    outcome: FlexibleShadowOutcome
    productive_status: str
    shadow_status: str
    divergence_categories: tuple[str, ...] = ()

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
    """Flexible shadow snapshot: master flexible on, preexistence off. Never materializes."""
    return PositionCompatibilityPolicy.resolve(
        signature_validation_enabled=legacy.signature_validation_enabled,
        allow_unsigned_legacy=legacy.allow_unsigned_legacy,
        preexistence_required=False,
        flexible_validation_enabled=True,
        signature_policy=legacy.signature_policy,
    )


def _status_family(status: CanonicalPositionValidationStatus) -> str | None:
    if status in _SIGNATURE_STATUSES:
        return FlexibleShadowDivergenceCategory.SIGNATURE.value
    if status in _PREEXISTENCE_STATUSES:
        return FlexibleShadowDivergenceCategory.PREEXISTENCE.value
    if status in _CLASSIFICATION_STATUSES:
        return FlexibleShadowDivergenceCategory.CLASSIFICATION.value
    if status in _FORMAT_STATUSES:
        return FlexibleShadowDivergenceCategory.FORMAT.value
    if status in _SCOPE_STATUSES:
        return FlexibleShadowDivergenceCategory.SCOPE.value
    return None


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

    categories: list[str] = []
    if productive.status != shadow.status:
        for side in (productive.status, shadow.status):
            family = _status_family(side)
            if family:
                categories.append(family)
        # Flexible accepts an unmaterialized candidate → materialization becomes possible.
        if (
            shadow.status is CanonicalPositionValidationStatus.VALID_UNMATERIALIZED
            and productive.status
            is CanonicalPositionValidationStatus.PREEXISTENCE_REQUIRED_BY_LEGACY_POLICY
        ):
            categories.append(
                FlexibleShadowDivergenceCategory.MATERIALIZATION_POSSIBLE.value
            )
        if not categories and outcome in {
            FlexibleShadowOutcome.DIVERGENCE_FLEXIBLE_ACCEPTS,
            FlexibleShadowOutcome.DIVERGENCE_FLEXIBLE_REJECTS,
        }:
            categories.append(FlexibleShadowDivergenceCategory.OTHER.value)

    return FlexibleShadowComparison(
        outcome=outcome,
        productive_status=productive.status.value,
        shadow_status=shadow.status.value,
        divergence_categories=tuple(dict.fromkeys(categories)),
    )


class PositionFlexibleShadowEvaluator:
    """Run flexible policy in shadow; never change productive accept/reject or materialize."""

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
            for category in comparison.divergence_categories or ("OTHER",):
                record_position_flexible_divergence(
                    channel=self._channel.value,
                    outcome=comparison.outcome.value,
                    category=category,
                )
        return FlexibleShadowEvaluation(
            productive=productive,
            shadow=shadow,
            comparison=comparison,
        )
