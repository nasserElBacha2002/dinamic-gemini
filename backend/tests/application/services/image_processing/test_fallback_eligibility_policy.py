"""Unit tests for Phase 5 FallbackEligibilityPolicy."""

from __future__ import annotations

from src.application.services.image_processing.fallback_eligibility_policy import (
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
) -> ImageProcessingResult:
    return ImageProcessingResult(
        job_id="j1",
        asset_id="a1",
        status=status,
        processing_mode="CODE_SCAN",
        error_code=error_code,
        execution_scope=ExecutionScope.SINGLE_ASSET,
        logical_asset_attempt=False,
    )


def test_resolved_internal_not_eligible() -> None:
    policy = FallbackEligibilityPolicy(enabled=True)
    d = policy.evaluate(_result(ImageResultStatus.RESOLVED_INTERNAL))
    assert d.eligible is False
    assert d.reason == "ALREADY_RESOLVED_INTERNAL"


def test_unrecognized_eligible() -> None:
    policy = FallbackEligibilityPolicy(enabled=True)
    d = policy.evaluate(_result(ImageResultStatus.UNRECOGNIZED))
    assert d.eligible is True


def test_missing_quantity_manual_review_eligible() -> None:
    policy = FallbackEligibilityPolicy(enabled=True)
    d = policy.evaluate(
        _result(ImageResultStatus.PENDING_MANUAL_REVIEW, error_code="MISSING_QUANTITY")
    )
    assert d.eligible is True


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


def test_recoverable_technical_eligible() -> None:
    policy = FallbackEligibilityPolicy(enabled=True)
    d = policy.evaluate(
        _result(ImageResultStatus.FAILED_TECHNICAL, error_code="INTERNAL_OCR_TIMEOUT")
    )
    assert d.eligible is True


def test_non_recoverable_technical_not_eligible() -> None:
    policy = FallbackEligibilityPolicy(enabled=True)
    d = policy.evaluate(
        _result(ImageResultStatus.FAILED_TECHNICAL, error_code="SOME_OTHER_ERROR")
    )
    assert d.eligible is False
