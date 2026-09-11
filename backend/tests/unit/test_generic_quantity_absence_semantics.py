"""Quantity absence must not invent zero; incomplete enrichment stays eligible."""

from __future__ import annotations

from src.application.services.image_processing.fallback_eligibility_policy import (
    FallbackEligibilityPolicy,
)
from src.application.services.image_processing.processing_result_persister import (
    _product_specs_from_result,
)
from src.domain.image_processing.contracts import ImageProcessingResult, ImageResultStatus


def test_product_specs_skip_when_quantity_missing() -> None:
    result = ImageProcessingResult(
        job_id="j1",
        asset_id="a1",
        status=ImageResultStatus.RESOLVED_INTERNAL,
        processing_mode="CODE_SCAN",
        internal_code="PRD-123456",
        quantity=None,
    )
    assert _product_specs_from_result(result) == []


def test_fallback_identity_only_not_already_resolved_when_eligible() -> None:
    policy = FallbackEligibilityPolicy(enabled=True)
    result = ImageProcessingResult(
        job_id="j1",
        asset_id="a1",
        status=ImageResultStatus.RESOLVED_INTERNAL,
        processing_mode="CODE_SCAN",
        internal_code="PRD-123456",
        quantity=None,
        evidence={
            "identity_valid": True,
            "enrichment_complete": False,
            "fallback_eligible": True,
        },
        validation_errors=["MISSING_QUANTITY"],
        error_code="MISSING_QUANTITY",
    )
    decision = policy.evaluate(result)
    assert decision.eligible is True
    assert decision.reason == "MISSING_QUANTITY"


def test_fallback_identity_only_denies_when_policy_false() -> None:
    policy = FallbackEligibilityPolicy(enabled=True)
    result = ImageProcessingResult(
        job_id="j1",
        asset_id="a1",
        status=ImageResultStatus.RESOLVED_INTERNAL,
        processing_mode="CODE_SCAN",
        internal_code="PRD-123456",
        quantity=None,
        evidence={
            "identity_valid": True,
            "enrichment_complete": False,
            "fallback_eligible": False,
        },
    )
    decision = policy.evaluate(result)
    assert decision.eligible is False
    assert decision.reason == "MISSING_QUANTITY_POLICY_DENIES"
