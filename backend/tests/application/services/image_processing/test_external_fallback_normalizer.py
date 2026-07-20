"""Unit tests for Phase 5 ExternalResultNormalizer + circuit breaker."""

from __future__ import annotations

from src.application.ports.external_image_analysis_provider import (
    ExternalAnalysisResult,
    ExternalAnalysisStatus,
)
from src.application.services.image_processing.external_circuit_breaker import (
    ExternalCircuitBreaker,
)
from src.application.services.image_processing.external_result_normalizer import (
    ExternalResultNormalizer,
)
from src.domain.image_processing.contracts import ImageResultStatus


def test_valid_external_normalizes_to_resolved_external() -> None:
    n = ExternalResultNormalizer()
    result = n.normalize(
        job_id="j1",
        asset_id="a1",
        analysis=ExternalAnalysisResult(
            status=ExternalAnalysisStatus.VALID,
            internal_code="7791234567890",
            quantity=48,
            provider_name="gemini",
            model_name="m",
        ),
    )
    assert result.status is ImageResultStatus.RESOLVED_EXTERNAL
    assert result.internal_code == "7791234567890"
    assert result.quantity == 48.0


def test_ambiguous_goes_to_manual_review() -> None:
    n = ExternalResultNormalizer()
    result = n.normalize(
        job_id="j1",
        asset_id="a1",
        analysis=ExternalAnalysisResult(status=ExternalAnalysisStatus.AMBIGUOUS),
    )
    assert result.status is ImageResultStatus.PENDING_MANUAL_REVIEW


def test_no_result_unrecognized() -> None:
    n = ExternalResultNormalizer()
    result = n.normalize(
        job_id="j1",
        asset_id="a1",
        analysis=ExternalAnalysisResult(status=ExternalAnalysisStatus.NO_RESULT),
    )
    assert result.status is ImageResultStatus.UNRECOGNIZED


def test_valid_missing_quantity_not_resolved() -> None:
    n = ExternalResultNormalizer()
    result = n.normalize(
        job_id="j1",
        asset_id="a1",
        analysis=ExternalAnalysisResult(
            status=ExternalAnalysisStatus.VALID,
            internal_code="ABC",
            quantity=None,
        ),
    )
    assert result.status is ImageResultStatus.PENDING_MANUAL_REVIEW
    assert "MISSING_QUANTITY" in result.validation_errors


def test_circuit_breaker_opens_after_threshold() -> None:
    cb = ExternalCircuitBreaker(failure_threshold=2, cooldown_seconds=60)
    assert cb.is_open("gemini", "m") is False
    cb.record_failure("gemini", "m")
    assert cb.is_open("gemini", "m") is False
    cb.record_failure("gemini", "m")
    assert cb.is_open("gemini", "m") is True
    cb.record_success("gemini", "m")
    assert cb.is_open("gemini", "m") is False
