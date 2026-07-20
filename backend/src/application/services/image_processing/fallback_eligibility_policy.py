"""Decide whether an internal ImageProcessingResult may call an external provider.

Technical failures never trigger AI/external fallback by default. Business
non-resolutions (missing code, missing quantity per policy, optional ambiguity)
may be eligible when the feature flag / job snapshot enables fallback.

Precedence (highest first):
1. fallback disabled
2. already resolved
3. technical / never-eligible errors
4. total absence of internal_code (before ambiguity)
5. code present with missing quantity (policy flag)
6. code present with ambiguity (ambiguous flag)
7. other statuses
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

_AMBIGUITY_MARKERS = frozenset(
    {
        "AMBIGUOUS_INTERNAL_CODE",
        "AMBIGUOUS_EXTERNAL",
    }
)


@dataclass(frozen=True)
class FallbackDecision:
    eligible: bool
    reason: str
    next_strategy: str | None = None


# Backward-compatible alias (Phase 5 tests / imports).
FallbackEligibilityDecision = FallbackDecision


@dataclass(frozen=True)
class InternalResultFacts:
    """Structured facts derived from an internal ImageProcessingResult."""

    has_internal_code: bool
    has_quantity: bool
    is_unrecognized: bool
    is_manual_review: bool
    is_technical_failure: bool
    has_missing_code_error: bool
    has_missing_quantity_error: bool
    has_ambiguity_error: bool
    error_codes: frozenset[str]


def _error_codes(result: ImageProcessingResult) -> frozenset[str]:
    codes: set[str] = set()
    if result.error_code:
        codes.add(str(result.error_code).strip().upper())
    for item in result.validation_errors or []:
        text = str(item).strip().upper()
        if text:
            codes.add(text)
    return frozenset(codes)


def _evidence_flag(result: ImageProcessingResult, key: str) -> bool | None:
    for bag in (result.evidence, result.additional_fields):
        if isinstance(bag, dict) and key in bag:
            return bool(bag[key])
    return None


def classify_internal_result(result: ImageProcessingResult) -> InternalResultFacts:
    codes = _error_codes(result)
    return InternalResultFacts(
        has_internal_code=bool(result.internal_code and str(result.internal_code).strip()),
        has_quantity=result.quantity is not None,
        is_unrecognized=result.status is ImageResultStatus.UNRECOGNIZED,
        is_manual_review=result.status is ImageResultStatus.PENDING_MANUAL_REVIEW,
        is_technical_failure=result.status is ImageResultStatus.FAILED_TECHNICAL,
        has_missing_code_error=bool(codes & _ELIGIBLE_MISSING_CODE_MARKERS),
        has_missing_quantity_error="MISSING_QUANTITY" in codes,
        has_ambiguity_error=bool(codes & _AMBIGUITY_MARKERS),
        error_codes=codes,
    )


@dataclass(frozen=True)
class FallbackEligibilityPolicy:
    """Pure policy: given an internal result, decide external fallback eligibility."""

    enabled: bool = False
    recoverable_technical_codes: frozenset[str] = DEFAULT_RECOVERABLE_TECHNICAL_CODES
    ambiguous_internal_code_fallback_enabled: bool = False

    def evaluate(self, result: ImageProcessingResult) -> FallbackDecision:
        facts = classify_internal_result(result)

        # 1. Fallback disabled
        if not self.enabled:
            return FallbackDecision(False, "FALLBACK_DISABLED")

        # 2. Already resolved
        if result.status is ImageResultStatus.RESOLVED_INTERNAL:
            return FallbackDecision(False, "ALREADY_RESOLVED")
        if result.status is ImageResultStatus.RESOLVED_EXTERNAL:
            return FallbackDecision(False, "ALREADY_RESOLVED")

        # 3. Technical / never-eligible error codes
        blocked = facts.error_codes & (
            NEVER_ELIGIBLE_ERROR_CODES | TECHNICAL_NEVER_ELIGIBLE_ERROR_CODES
        )
        if blocked:
            code = sorted(blocked)[0]
            return FallbackDecision(False, f"NOT_ELIGIBLE:{code}")

        if facts.is_technical_failure:
            primary = (result.error_code or "").strip().upper()
            if primary and primary in self.recoverable_technical_codes:
                if primary in TECHNICAL_NEVER_ELIGIBLE_ERROR_CODES:
                    return FallbackDecision(False, f"NOT_ELIGIBLE:{primary}")
                return FallbackDecision(
                    True,
                    f"RECOVERABLE_TECHNICAL:{primary}",
                    EXTERNAL_PROVIDER_STRATEGY,
                )
            return FallbackDecision(False, "TECHNICAL_FAILURE_NOT_ELIGIBLE")

        # 4. Total absence of internal_code — before ambiguity.
        # Ambiguity among discarded OCR candidates is only diagnostic when nothing was selected.
        # Manual review without an allowlisted missing-code reason must NOT trigger AI.
        if not facts.has_internal_code:
            if facts.is_unrecognized or facts.has_missing_code_error:
                return FallbackDecision(
                    True,
                    "MISSING_INTERNAL_CODE",
                    EXTERNAL_PROVIDER_STRATEGY,
                )
            return FallbackDecision(False, "STATUS_NOT_ELIGIBLE")

        # 5. Code present, quantity missing
        if facts.has_missing_quantity_error and not facts.has_quantity:
            allow = _evidence_flag(result, "fallback_eligible")
            if allow is False:
                return FallbackDecision(False, "MISSING_QUANTITY_POLICY_DENIES")
            if allow is True:
                return FallbackDecision(
                    True,
                    "MISSING_QUANTITY",
                    EXTERNAL_PROVIDER_STRATEGY,
                )
            return FallbackDecision(False, "MISSING_QUANTITY_POLICY_UNSPECIFIED")

        # 6. Code present with ambiguity — controlled by dedicated flag
        if facts.has_ambiguity_error:
            if self.ambiguous_internal_code_fallback_enabled:
                return FallbackDecision(
                    True,
                    "AMBIGUOUS_INTERNAL_CODE",
                    EXTERNAL_PROVIDER_STRATEGY,
                )
            return FallbackDecision(False, "AMBIGUITY_POLICY_DENIES")

        # 7. Other statuses
        if facts.is_unrecognized:
            return FallbackDecision(False, "UNRECOGNIZED_NOT_ELIGIBLE")
        if facts.is_manual_review:
            return FallbackDecision(False, "PENDING_MANUAL_REVIEW_NOT_ELIGIBLE")

        return FallbackDecision(False, "STATUS_NOT_ELIGIBLE")


__all__ = [
    "DEFAULT_RECOVERABLE_TECHNICAL_CODES",
    "EXTERNAL_PROVIDER_STRATEGY",
    "FallbackDecision",
    "FallbackEligibilityDecision",
    "FallbackEligibilityPolicy",
    "InternalResultFacts",
    "NEVER_ELIGIBLE_ERROR_CODES",
    "TECHNICAL_NEVER_ELIGIBLE_ERROR_CODES",
    "classify_internal_result",
]
