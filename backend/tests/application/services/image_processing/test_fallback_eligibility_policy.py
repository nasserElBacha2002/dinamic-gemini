"""Unit tests for FallbackEligibilityPolicy (selective external fallback)."""

from __future__ import annotations

from src.application.services.image_processing.fallback_eligibility_policy import (
    EXTERNAL_PROVIDER_STRATEGY,
    FallbackEligibilityPolicy,
)
from src.domain.image_processing.contracts import (
    ExecutionScope,
    ImageProcessingResult,
    ImageResultStatus,
)


def _result(
    status: ImageResultStatus,
    *,
    error_code: str | None = None,
    validation_errors: list[str] | None = None,
    internal_code: str | None = None,
    quantity: float | None = None,
    evidence: dict | None = None,
) -> ImageProcessingResult:
    return ImageProcessingResult(
        job_id="j1",
        asset_id="a1",
        status=status,
        processing_mode="INTERNAL_OCR",
        internal_code=internal_code,
        quantity=quantity,
        error_code=error_code,
        validation_errors=list(validation_errors or []),
        evidence=evidence,
        execution_scope=ExecutionScope.SINGLE_ASSET,
        logical_asset_attempt=False,
    )


def test_resolved_internal_not_eligible() -> None:
    policy = FallbackEligibilityPolicy(enabled=True)
    d = policy.evaluate(_result(ImageResultStatus.RESOLVED_INTERNAL))
    assert d.eligible is False
    assert d.reason == "ALREADY_RESOLVED"
    assert d.next_strategy is None


def test_incident_unrecognized_ambiguous_without_code_is_eligible() -> None:
    """Job 813e0849: AMBIGUOUS + MISSING with null code must still fallback."""
    policy = FallbackEligibilityPolicy(enabled=True, ambiguous_internal_code_fallback_enabled=False)
    d = policy.evaluate(
        _result(
            ImageResultStatus.UNRECOGNIZED,
            error_code="AMBIGUOUS_INTERNAL_CODE",
            validation_errors=[
                "AMBIGUOUS_INTERNAL_CODE",
                "MISSING_INTERNAL_CODE",
                "MISSING_QUANTITY",
            ],
            internal_code=None,
            quantity=None,
        )
    )
    assert d.eligible is True
    assert d.reason == "MISSING_INTERNAL_CODE"
    assert d.next_strategy == EXTERNAL_PROVIDER_STRATEGY


def test_unrecognized_missing_code_eligible() -> None:
    policy = FallbackEligibilityPolicy(enabled=True)
    d = policy.evaluate(
        _result(
            ImageResultStatus.UNRECOGNIZED,
            error_code="MISSING_INTERNAL_CODE",
            validation_errors=["MISSING_INTERNAL_CODE", "MISSING_QUANTITY"],
        )
    )
    assert d.eligible is True
    assert d.reason == "MISSING_INTERNAL_CODE"
    assert d.next_strategy == EXTERNAL_PROVIDER_STRATEGY


def test_missing_quantity_eligible_when_policy_allows() -> None:
    policy = FallbackEligibilityPolicy(enabled=True)
    d = policy.evaluate(
        _result(
            ImageResultStatus.PENDING_MANUAL_REVIEW,
            error_code="MISSING_QUANTITY",
            internal_code="1234567",
            evidence={"fallback_eligible": True},
        )
    )
    assert d.eligible is True
    assert d.reason == "MISSING_QUANTITY"
    assert d.next_strategy == EXTERNAL_PROVIDER_STRATEGY


def test_missing_quantity_denied_when_policy_disallows() -> None:
    policy = FallbackEligibilityPolicy(enabled=True)
    d = policy.evaluate(
        _result(
            ImageResultStatus.PENDING_MANUAL_REVIEW,
            error_code="MISSING_QUANTITY",
            internal_code="1234567",
            evidence={"fallback_eligible": False},
        )
    )
    assert d.eligible is False
    assert d.reason == "MISSING_QUANTITY_POLICY_DENIES"


def test_missing_quantity_unspecified_not_eligible() -> None:
    policy = FallbackEligibilityPolicy(enabled=True)
    d = policy.evaluate(
        _result(
            ImageResultStatus.PENDING_MANUAL_REVIEW,
            error_code="MISSING_QUANTITY",
            internal_code="1234567",
        )
    )
    assert d.eligible is False
    assert d.reason == "MISSING_QUANTITY_POLICY_UNSPECIFIED"


def test_ambiguous_with_code_requires_flag_false() -> None:
    denied = FallbackEligibilityPolicy(enabled=True, ambiguous_internal_code_fallback_enabled=False)
    d = denied.evaluate(
        _result(
            ImageResultStatus.PENDING_MANUAL_REVIEW,
            error_code="AMBIGUOUS_INTERNAL_CODE",
            internal_code="PARTIAL123",
        )
    )
    assert d.eligible is False
    assert d.reason == "AMBIGUITY_POLICY_DENIES"


def test_ambiguous_with_code_requires_flag_true() -> None:
    allowed = FallbackEligibilityPolicy(enabled=True, ambiguous_internal_code_fallback_enabled=True)
    d2 = allowed.evaluate(
        _result(
            ImageResultStatus.PENDING_MANUAL_REVIEW,
            error_code="AMBIGUOUS_INTERNAL_CODE",
            internal_code="PARTIAL123",
        )
    )
    assert d2.eligible is True
    assert d2.next_strategy == EXTERNAL_PROVIDER_STRATEGY


def test_persistence_failure_not_eligible() -> None:
    policy = FallbackEligibilityPolicy(enabled=True)
    d = policy.evaluate(
        _result(
            ImageResultStatus.FAILED_TECHNICAL,
            error_code="PROCESSING_PERSISTENCE_FAILED",
        )
    )
    assert d.eligible is False


def test_feature_flag_disabled() -> None:
    policy = FallbackEligibilityPolicy(enabled=False)
    d = policy.evaluate(_result(ImageResultStatus.UNRECOGNIZED))
    assert d.eligible is False
    assert d.reason == "FALLBACK_DISABLED"


def test_technical_timeout_never_eligible() -> None:
    policy = FallbackEligibilityPolicy(enabled=True)
    d = policy.evaluate(
        _result(ImageResultStatus.FAILED_TECHNICAL, error_code="INTERNAL_OCR_TIMEOUT")
    )
    assert d.eligible is False
    assert "NOT_ELIGIBLE" in d.reason or d.reason == "TECHNICAL_FAILURE_NOT_ELIGIBLE"


def test_source_asset_read_failed_not_eligible() -> None:
    policy = FallbackEligibilityPolicy(enabled=True)
    d = policy.evaluate(
        _result(
            ImageResultStatus.FAILED_TECHNICAL,
            error_code="SOURCE_ASSET_READ_FAILED",
        )
    )
    assert d.eligible is False


def test_pending_manual_review_length_reject_not_eligible() -> None:
    """Profile length/anchor rejects stay for operator review — not AI."""
    policy = FallbackEligibilityPolicy(enabled=True)
    d = policy.evaluate(
        _result(
            ImageResultStatus.PENDING_MANUAL_REVIEW,
            error_code="CODE_LENGTH_NOT_EXACT",
            validation_errors=["CODE_LENGTH_NOT_EXACT", "CODE_UNANCHORED_NOT_ALLOWED"],
            internal_code="1234567",
        )
    )
    assert d.eligible is False
    assert d.reason == "PENDING_MANUAL_REVIEW_NOT_ELIGIBLE"


def test_manual_review_unsupported_format_without_code_not_eligible() -> None:
    policy = FallbackEligibilityPolicy(enabled=True)
    d = policy.evaluate(
        _result(
            ImageResultStatus.PENDING_MANUAL_REVIEW,
            error_code="UNSUPPORTED_BARCODE_FORMAT",
            validation_errors=["UNSUPPORTED_BARCODE_FORMAT"],
            internal_code=None,
        )
    )
    assert d.eligible is False
    assert d.reason == "STATUS_NOT_ELIGIBLE"


def test_manual_review_forbidden_source_without_code_not_eligible() -> None:
    policy = FallbackEligibilityPolicy(enabled=True)
    d = policy.evaluate(
        _result(
            ImageResultStatus.PENDING_MANUAL_REVIEW,
            error_code="FORBIDDEN_SOURCE",
            validation_errors=["FORBIDDEN_SOURCE"],
            internal_code=None,
        )
    )
    assert d.eligible is False
    assert d.reason == "STATUS_NOT_ELIGIBLE"


def test_manual_review_with_missing_code_marker_is_eligible() -> None:
    policy = FallbackEligibilityPolicy(enabled=True)
    d = policy.evaluate(
        _result(
            ImageResultStatus.PENDING_MANUAL_REVIEW,
            error_code="MISSING_INTERNAL_CODE",
            validation_errors=["MISSING_INTERNAL_CODE"],
            internal_code=None,
        )
    )
    assert d.eligible is True
    assert d.reason == "MISSING_INTERNAL_CODE"
    assert d.next_strategy == EXTERNAL_PROVIDER_STRATEGY


def test_manual_review_bare_without_code_not_eligible() -> None:
    """PENDING_MANUAL_REVIEW alone must not trigger AI when no missing-code marker."""
    policy = FallbackEligibilityPolicy(enabled=True)
    d = policy.evaluate(
        _result(
            ImageResultStatus.PENDING_MANUAL_REVIEW,
            error_code="UNSUPPORTED_LABEL_LAYOUT",
            internal_code=None,
        )
    )
    assert d.eligible is False
    assert d.reason == "STATUS_NOT_ELIGIBLE"
