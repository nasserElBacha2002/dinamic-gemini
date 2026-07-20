"""Phase 5 — decide whether an internal ImageProcessingResult may call an external provider."""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.image_processing.contracts import ImageProcessingResult, ImageResultStatus

# Technical error codes that MAY trigger external fallback (explicit allowlist).
DEFAULT_RECOVERABLE_TECHNICAL_CODES = frozenset(
    {
        "INTERNAL_OCR_TIMEOUT",
        "INTERNAL_OCR_ENGINE_UNAVAILABLE",
        "CODE_SCAN_TIMEOUT",
        "CODE_SCAN_SCANNER_ERROR",
        "SOURCE_ASSET_READ_FAILED",
    }
)

# Never eligible regardless of status.
NEVER_ELIGIBLE_ERROR_CODES = frozenset(
    {
        "PROCESSING_PERSISTENCE_FAILED",
        "ASSET_NOT_IN_JOB_SNAPSHOT",
        "MANUAL_RESULT_EXISTS",
        "STATE_CONCURRENCY_CONFLICT",
        "CODE_SCAN_PIPELINE_MISCONFIGURED",
        "INTERNAL_OCR_PIPELINE_MISCONFIGURED",
    }
)


@dataclass(frozen=True)
class FallbackEligibilityDecision:
    eligible: bool
    reason: str


@dataclass(frozen=True)
class FallbackEligibilityPolicy:
    """Pure policy: given an internal result, decide external fallback eligibility."""

    enabled: bool = False
    recoverable_technical_codes: frozenset[str] = DEFAULT_RECOVERABLE_TECHNICAL_CODES

    def evaluate(self, result: ImageProcessingResult) -> FallbackEligibilityDecision:
        if not self.enabled:
            return FallbackEligibilityDecision(False, "FALLBACK_DISABLED")

        if result.status is ImageResultStatus.RESOLVED_INTERNAL:
            return FallbackEligibilityDecision(False, "ALREADY_RESOLVED_INTERNAL")
        if result.status is ImageResultStatus.RESOLVED_EXTERNAL:
            return FallbackEligibilityDecision(False, "ALREADY_RESOLVED_EXTERNAL")

        error_code = (result.error_code or "").strip().upper()
        if error_code in NEVER_ELIGIBLE_ERROR_CODES:
            return FallbackEligibilityDecision(False, f"NOT_ELIGIBLE:{error_code}")

        if result.status is ImageResultStatus.UNRECOGNIZED:
            return FallbackEligibilityDecision(True, "UNRECOGNIZED")

        if result.status is ImageResultStatus.PENDING_MANUAL_REVIEW:
            # Missing code/qty, ambiguity, low confidence — eligible.
            return FallbackEligibilityDecision(True, "PENDING_MANUAL_REVIEW")

        if result.status is ImageResultStatus.FAILED_TECHNICAL:
            if error_code and error_code in self.recoverable_technical_codes:
                return FallbackEligibilityDecision(True, f"RECOVERABLE_TECHNICAL:{error_code}")
            return FallbackEligibilityDecision(False, "TECHNICAL_NOT_RECOVERABLE")

        return FallbackEligibilityDecision(False, "STATUS_NOT_ELIGIBLE")


__all__ = [
    "DEFAULT_RECOVERABLE_TECHNICAL_CODES",
    "FallbackEligibilityDecision",
    "FallbackEligibilityPolicy",
    "NEVER_ELIGIBLE_ERROR_CODES",
]
