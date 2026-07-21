"""Tests for external fallback Gemini response parse / schema separation."""

from __future__ import annotations

from src.application.ports.external_image_analysis_provider import ExternalAnalysisStatus
from src.application.services.image_processing.external_result_normalizer import (
    ExternalResultNormalizer,
)
from src.domain.image_processing.contracts import ImageResultStatus
from src.infrastructure.image_processing.llm_external_image_analysis_provider import (
    parse_external_fallback_payload,
)


def test_valid_json_with_code_and_quantity() -> None:
    analysis = parse_external_fallback_payload(
        {"status": "VALID", "internal_code": "ABC123", "quantity": 20}
    )
    assert analysis.status is ExternalAnalysisStatus.VALID
    assert analysis.internal_code == "ABC123"
    assert analysis.quantity == 20
    result = ExternalResultNormalizer().normalize(
        job_id="j", asset_id="a", analysis=analysis
    )
    assert result.status is ImageResultStatus.RESOLVED_EXTERNAL


def test_code_without_quantity_is_manual_review() -> None:
    analysis = parse_external_fallback_payload(
        {"status": "VALID", "internal_code": "ABC123", "quantity": None}
    )
    result = ExternalResultNormalizer().normalize(
        job_id="j", asset_id="a", analysis=analysis
    )
    assert result.status is ImageResultStatus.PENDING_MANUAL_REVIEW
    assert "MISSING_QUANTITY" in result.validation_errors


def test_explicit_no_result() -> None:
    analysis = parse_external_fallback_payload(
        {"status": "NO_RESULT", "internal_code": None, "quantity": None, "reason": "blank"}
    )
    assert analysis.status is ExternalAnalysisStatus.NO_RESULT
    assert analysis.error_code == "EXTERNAL_NO_RESULT"
    result = ExternalResultNormalizer().normalize(
        job_id="j", asset_id="a", analysis=analysis
    )
    assert result.status is ImageResultStatus.UNRECOGNIZED
    assert result.error_code == "EXTERNAL_NO_RESULT"
    assert (result.additional_fields or {}).get("provider_declared_no_result") is True


def test_empty_response_is_technical() -> None:
    analysis = parse_external_fallback_payload(None, raw_text="")
    assert analysis.status is ExternalAnalysisStatus.FAILED_TECHNICAL
    assert analysis.error_code == "EXTERNAL_EMPTY_RESPONSE"
    result = ExternalResultNormalizer().normalize(
        job_id="j", asset_id="a", analysis=analysis
    )
    assert result.status is ImageResultStatus.FAILED_TECHNICAL


def test_markdown_fenced_handled_by_caller_aliases() -> None:
    # Parser receives already-decoded object; aliases covered here.
    analysis = parse_external_fallback_payload(
        {"status": "VALID", "internalCode": "X1", "cantidad": "7"}
    )
    assert analysis.internal_code == "X1"
    assert analysis.quantity == 7


def test_hybrid_v21_schema_is_not_external_no_result() -> None:
    """Incident a22bb927 root cause: hybrid entities must not collapse to NO_RESULT."""
    analysis = parse_external_fallback_payload(
        {
            "total_entities_detected": 1,
            "entities": [
                {
                    "entity_type": "PALLET",
                    "internal_code": "SHOULD_NOT_SILENTLY_DROP",
                    "product_label_quantity": 12,
                    "has_boxes": True,
                    "confidence": 0.9,
                }
            ],
        }
    )
    assert analysis.status is ExternalAnalysisStatus.FAILED_TECHNICAL
    assert analysis.error_code == "EXTERNAL_HYBRID_SCHEMA_MISROUTED"
    result = ExternalResultNormalizer().normalize(
        job_id="j", asset_id="a", analysis=analysis
    )
    assert result.status is ImageResultStatus.FAILED_TECHNICAL
    assert result.error_code == "EXTERNAL_HYBRID_SCHEMA_MISROUTED"


def test_unknown_status_is_schema_invalid() -> None:
    analysis = parse_external_fallback_payload({"status": "MAYBE", "internal_code": None})
    assert analysis.error_code == "EXTERNAL_SCHEMA_INVALID"
    assert (analysis.additional_fields or {}).get("schema_validation", {}).get(
        "reason_code"
    ) == "UNKNOWN_STATUS"


def test_invalid_quantity_type_is_structured_schema_error() -> None:
    analysis = parse_external_fallback_payload(
        {"status": "VALID", "internal_code": "A", "quantity": "twelve"},
        raw_text='{"status":"VALID","quantity":"twelve"}',
    )
    assert analysis.error_code == "EXTERNAL_SCHEMA_INVALID"
    schema = (analysis.additional_fields or {}).get("schema_validation") or {}
    assert schema.get("field") == "quantity"
    assert schema.get("reason_code") == "INVALID_TYPE"
    assert analysis.raw_reference is not None


def test_invalid_confidence_type_is_structured_schema_error() -> None:
    analysis = parse_external_fallback_payload(
        {"status": "VALID", "internal_code": "A", "quantity": 1, "confidence": "high"},
        raw_text='{"confidence":"high"}',
    )
    assert analysis.error_code == "EXTERNAL_SCHEMA_INVALID"
    schema = (analysis.additional_fields or {}).get("schema_validation") or {}
    assert schema.get("field") == "confidence"


def test_extra_fields_are_ignored_when_contract_fields_valid() -> None:
    analysis = parse_external_fallback_payload(
        {
            "status": "VALID",
            "internal_code": "SKU1",
            "quantity": 2,
            "unexpected_vendor_field": {"nested": True},
        }
    )
    assert analysis.status is ExternalAnalysisStatus.VALID
    assert analysis.internal_code == "SKU1"
    assert analysis.quantity == 2
