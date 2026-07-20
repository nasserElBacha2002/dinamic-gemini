"""Decide whether an internal ImageProcessingResult may call an external provider.

Technical failures never trigger AI/external fallback by default. Business
non-resolutions (missing code, missing quantity per policy, optional ambiguity)
may be eligible when the feature flag / job snapshot enables fallback.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.image_processing.contracts import ImageProcessingResult, ImageResultStatus

EXTERNAL_PROVIDER_STRATEGY = "EXTERNAL_PROVIDER"

# Historical name retained for snapshot/API compatibility. Default is empty:
# technical failures must not be routed to an external provider.
DEFAULT_RECOVERABLE_TECHNICAL_CODES: frozenset[str] = frozenset()

# Never eligible regardless of status (persistence / config / concurrency).
NEVER_ELIGIBLE_ERROR_CODES = frozenset(
    {
        "PROCESSING_PERSISTENCE_FAILED",
        "ASSET_NOT_IN_JOB_SNAPSHOT",
        "MANUAL_RESULT_EXISTS",
        "STATE_CONCURRENCY_CONFLICT",
        "CODE_SCAN_PIPELINE_MISCONFIGURED",
        "INTERNAL_OCR_PIPELINE_MISCONFIGURED",
        "PROFILE_SNAPSHOT_INVALID",
        "JOB_CANCELLED",
        "LEASE_LOST",
    }
)

# Source / engine / decode failures — never send to AI to paper over defects.
TECHNICAL_NEVER_ELIGIBLE_ERROR_CODES = frozenset(
    {
        "SOURCE_ASSET_NOT_FOUND",
        "SOURCE_ASSET_READ_FAILED",
        "SOURCE_ASSET_EMPTY",
        "OCR_IMAGE_DECODE_FAILED",
        "OCR_PREPROCESS_FAILED",
        "INTERNAL_OCR_TIMEOUT",
        "INTERNAL_OCR_ENGINE_UNAVAILABLE",
        "CODE_SCAN_TIMEOUT",
        "CODE_SCAN_SCANNER_ERROR",
        "UNHANDLED_WORKER_ERROR",
        "CODE_SCAN_STARTUP_FAILED",
        "JOB_STARTUP_NO_PROGRESS",
    }
)

_ELIGIBLE_MISSING_CODE_MARKERS = frozenset(
    {
        "MISSING_INTERNAL_CODE",
        "NO_INTERNAL_CODE",
        "MISSING_CODE",
    }
)


@dataclass(frozen=True)
class FallbackDecision:
    eligible: bool
    reason: str
    next_strategy: str | None = None


# Backward-compatible alias (Phase 5 tests / imports).
FallbackEligibilityDecision = FallbackDecision


def _error_codes(result: ImageProcessingResult) -> set[str]:
    codes: set[str] = set()
    if result.error_code:
        codes.add(str(result.error_code).strip().upper())
    for item in result.validation_errors or []:
        text = str(item).strip().upper()
        if text:
            codes.add(text)
    return codes


def _evidence_flag(result: ImageProcessingResult, key: str) -> bool | None:
    for bag in (result.evidence, result.additional_fields):
        if isinstance(bag, dict) and key in bag:
            return bool(bag[key])
    return None


@dataclass(frozen=True)
class FallbackEligibilityPolicy:
    """Pure policy: given an internal result, decide external fallback eligibility."""

    enabled: bool = False
    recoverable_technical_codes: frozenset[str] = DEFAULT_RECOVERABLE_TECHNICAL_CODES
    ambiguous_internal_code_fallback_enabled: bool = False

    def evaluate(self, result: ImageProcessingResult) -> FallbackDecision:
        if not self.enabled:
            return FallbackDecision(False, "FALLBACK_DISABLED")

        if result.status is ImageResultStatus.RESOLVED_INTERNAL:
            return FallbackDecision(False, "ALREADY_RESOLVED_INTERNAL")
        if result.status is ImageResultStatus.RESOLVED_EXTERNAL:
            return FallbackDecision(False, "ALREADY_RESOLVED_EXTERNAL")

        codes = _error_codes(result)

        blocked = codes & (NEVER_ELIGIBLE_ERROR_CODES | TECHNICAL_NEVER_ELIGIBLE_ERROR_CODES)
        if blocked:
            code = sorted(blocked)[0]
            return FallbackDecision(False, f"NOT_ELIGIBLE:{code}")

        if result.status is ImageResultStatus.FAILED_TECHNICAL:
            primary = (result.error_code or "").strip().upper()
            if primary and primary in self.recoverable_technical_codes:
                # Explicit snapshot allowlist only — never the technical-never set.
                if primary in TECHNICAL_NEVER_ELIGIBLE_ERROR_CODES:
                    return FallbackDecision(False, f"NOT_ELIGIBLE:{primary}")
                return FallbackDecision(
                    True,
                    f"RECOVERABLE_TECHNICAL:{primary}",
                    EXTERNAL_PROVIDER_STRATEGY,
                )
            return FallbackDecision(False, "TECHNICAL_NOT_RECOVERABLE")

        if "AMBIGUOUS_INTERNAL_CODE" in codes or "AMBIGUOUS_EXTERNAL" in codes:
            if self.ambiguous_internal_code_fallback_enabled:
                return FallbackDecision(
                    True,
                    "AMBIGUOUS_INTERNAL_CODE",
                    EXTERNAL_PROVIDER_STRATEGY,
                )
            return FallbackDecision(False, "AMBIGUOUS_REQUIRES_MANUAL_REVIEW")

        if "MISSING_QUANTITY" in codes and result.internal_code:
            allow = _evidence_flag(result, "fallback_eligible")
            if allow is False:
                return FallbackDecision(False, "MISSING_QUANTITY_POLICY_DENIES")
            if allow is True:
                return FallbackDecision(
                    True,
                    "MISSING_QUANTITY",
                    EXTERNAL_PROVIDER_STRATEGY,
                )
            # Policy flag absent: do not auto-call AI for code-without-qty.
            return FallbackDecision(False, "MISSING_QUANTITY_POLICY_UNSPECIFIED")

        if result.status is ImageResultStatus.UNRECOGNIZED:
            if codes & _ELIGIBLE_MISSING_CODE_MARKERS or not result.internal_code:
                return FallbackDecision(
                    True,
                    "UNRECOGNIZED",
                    EXTERNAL_PROVIDER_STRATEGY,
                )
            return FallbackDecision(False, "UNRECOGNIZED_NOT_ELIGIBLE")

        if result.status is ImageResultStatus.PENDING_MANUAL_REVIEW:
            if codes & _ELIGIBLE_MISSING_CODE_MARKERS and not result.internal_code:
                return FallbackDecision(
                    True,
                    "MISSING_INTERNAL_CODE",
                    EXTERNAL_PROVIDER_STRATEGY,
                )
            return FallbackDecision(False, "PENDING_MANUAL_REVIEW_NOT_ELIGIBLE")

        return FallbackDecision(False, "STATUS_NOT_ELIGIBLE")


__all__ = [
    "DEFAULT_RECOVERABLE_TECHNICAL_CODES",
    "EXTERNAL_PROVIDER_STRATEGY",
    "FallbackDecision",
    "FallbackEligibilityDecision",
    "FallbackEligibilityPolicy",
    "NEVER_ELIGIBLE_ERROR_CODES",
    "TECHNICAL_NEVER_ELIGIBLE_ERROR_CODES",
]
