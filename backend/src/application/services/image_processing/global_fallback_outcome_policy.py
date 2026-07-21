"""Outcome policy: external failure must not blindly wipe useful internal results."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.application.services.image_processing.global_fallback_eligibility import (
    GlobalFallbackEligibilityDecision,
)


class GlobalFallbackOutcomeSeverity(str, Enum):
    OK = "OK"
    COMPLETED_WITH_WARNING = "COMPLETED_WITH_WARNING"
    COMPLETED_WITH_TECHNICAL_ERRORS = "COMPLETED_WITH_TECHNICAL_ERRORS"
    FAILED_CONFIGURATION = "FAILED_CONFIGURATION"
    FAILED_TECHNICAL = "FAILED_TECHNICAL"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class GlobalFallbackOutcomeDecision:
    severity: GlobalFallbackOutcomeSeverity
    fail_job: bool
    error_code: str | None = None
    message: str | None = None


def decide_global_fallback_outcome(
    *,
    eligibility: GlobalFallbackEligibilityDecision | None,
    cancelled: bool = False,
    configuration_error: bool = False,
    configuration_code: str | None = None,
    configuration_message: str | None = None,
    persistence_inconsistent: bool = False,
    provider_failed: bool = False,
    provider_error_code: str | None = None,
    provider_error_message: str | None = None,
    no_result: bool = False,
) -> GlobalFallbackOutcomeDecision:
    if cancelled:
        return GlobalFallbackOutcomeDecision(
            severity=GlobalFallbackOutcomeSeverity.CANCELLED,
            fail_job=False,
            error_code="CANCELLED",
        )
    if configuration_error:
        return GlobalFallbackOutcomeDecision(
            severity=GlobalFallbackOutcomeSeverity.FAILED_CONFIGURATION,
            fail_job=True,
            error_code=configuration_code or "CONFIGURATION_ERROR",
            message=configuration_message,
        )
    if persistence_inconsistent:
        return GlobalFallbackOutcomeDecision(
            severity=GlobalFallbackOutcomeSeverity.FAILED_TECHNICAL,
            fail_job=True,
            error_code="FALLBACK_PERSISTENCE_INCONSISTENT",
            message=provider_error_message,
        )
    if provider_failed:
        resolved = int(eligibility.resolved_internal) if eligibility else 0
        total = int(eligibility.total_assets) if eligibility else 0
        if total > 0 and resolved == total:
            return GlobalFallbackOutcomeDecision(
                severity=GlobalFallbackOutcomeSeverity.COMPLETED_WITH_WARNING,
                fail_job=False,
                error_code=provider_error_code or "FALLBACK_PROVIDER_FAILED",
                message=provider_error_message,
            )
        if resolved > 0:
            return GlobalFallbackOutcomeDecision(
                severity=GlobalFallbackOutcomeSeverity.COMPLETED_WITH_TECHNICAL_ERRORS,
                fail_job=False,
                error_code=provider_error_code or "FALLBACK_PROVIDER_FAILED",
                message=provider_error_message,
            )
        return GlobalFallbackOutcomeDecision(
            severity=GlobalFallbackOutcomeSeverity.FAILED_TECHNICAL,
            fail_job=True,
            error_code=provider_error_code or "FALLBACK_BATCH_FAILED",
            message=provider_error_message,
        )
    if no_result:
        return GlobalFallbackOutcomeDecision(
            severity=GlobalFallbackOutcomeSeverity.COMPLETED_WITH_WARNING,
            fail_job=False,
            error_code="NO_RESULT",
            message="provider returned no entities",
        )
    return GlobalFallbackOutcomeDecision(
        severity=GlobalFallbackOutcomeSeverity.OK,
        fail_job=False,
    )
