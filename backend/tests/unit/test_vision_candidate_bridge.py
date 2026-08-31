"""Vision → CandidateLabel → LabelValidationService bridge (final phase)."""

from __future__ import annotations

from src.application.ports.external_image_analysis_provider import (
    ExternalAnalysisResult,
    ExternalAnalysisStatus,
)
from src.application.services.image_processing.fallback_eligibility_policy import (
    FallbackEligibilityPolicy,
)
from src.application.services.image_processing.vision_candidate_bridge import (
    candidate_from_vision_analysis,
    normalize_vision_via_label_validation,
)
from src.domain.client_supplier.extraction_profile import (
    CONFIGURATION_SCHEMA_VERSION_V2,
    DeterministicBarcodeRules,
    ExtractionProfileConfiguration,
    FieldMappingRule,
    FieldMappingSource,
    ItemLabelSemanticType,
    PayloadStructure,
    QuantityExtractionRules,
)
from src.domain.image_processing.contracts import ImageProcessingResult, ImageResultStatus
from src.domain.label_profiles.entities import ResolvedLabelProfile, ResolvedLabelProfiles
from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource
from src.domain.label_validation import RecognitionSource
from src.domain.label_validation.context import LabelValidationContext


def _profiles() -> ResolvedLabelProfiles:
    return ResolvedLabelProfiles(
        item=ResolvedLabelProfile(
            label_kind=LabelKind.ITEM,
            source=LabelProfileSource.SUPPLIER,
            client_supplier_id="sup-1",
            resolution_source="CLIENT_SUPPLIER",
        ),
        position=ResolvedLabelProfile(
            label_kind=LabelKind.POSITION,
            source=LabelProfileSource.DINAMIC,
            client_supplier_id=None,
            resolution_source="DINAMIC",
        ),
    )


def test_candidate_from_vision_prefers_raw_payload() -> None:
    analysis = ExternalAnalysisResult(
        status=ExternalAnalysisStatus.VALID,
        provider_name="gemini",
        model_name="x",
        internal_code="IGNORE",
        quantity=2,
        normalized_result={"raw_payload": "ABC|SKU1|2", "sku": "WRONG"},
    )
    cand = candidate_from_vision_analysis(analysis)
    assert cand is not None
    assert cand.raw_payload == "ABC|SKU1|2"
    assert cand.recognition_source is RecognitionSource.VISION


def test_vision_segmented_via_label_validation() -> None:
    cfg = ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        semantic_type=ItemLabelSemanticType.PRODUCT_SKU.value,
        required_fields=("sku", "quantity"),
        accepted_barcode_formats=("CODE128",),
        quantity_rules=QuantityExtractionRules(required=True, minimum=1),
        deterministic=DeterministicBarcodeRules(
            payload_structure=PayloadStructure.SEGMENTED,
            delimiter="|",
            expected_segment_count=3,
            field_mappings=(
                FieldMappingRule("label_id", FieldMappingSource.SEGMENT, segment_index=0),
                FieldMappingRule("sku", FieldMappingSource.SEGMENT, segment_index=1),
                FieldMappingRule("quantity", FieldMappingSource.SEGMENT, segment_index=2),
            ),
        ),
    )
    ctx = LabelValidationContext(
        resolved_profiles=_profiles(),
        item_extraction_configuration=cfg,
        job_id="job-1",
    )
    analysis = ExternalAnalysisResult(
        status=ExternalAnalysisStatus.VALID,
        provider_name="gemini",
        model_name="x",
        normalized_result={"raw_payload": "L1|SKU99|3"},
        duration_ms=12,
    )
    out = normalize_vision_via_label_validation(
        job_id="job-1",
        asset_id="a1",
        analysis=analysis,
        validation_context=ctx,
        base_fields={},
        evidence={},
    )
    assert out.status is ImageResultStatus.RESOLVED_EXTERNAL
    assert out.product_results
    assert out.product_results[0].internal_code == "SKU99"
    assert out.product_results[0].quantity == 3
    assert out.evidence.get("vision_unified_validation") is True


def test_d1_invalid_not_eligible_for_vision() -> None:
    policy = FallbackEligibilityPolicy(enabled=True)
    result = ImageProcessingResult(
        job_id="j",
        asset_id="a",
        status=ImageResultStatus.UNRECOGNIZED,
        processing_mode="CODE_SCAN",
        resolved_by="CODE_SCAN",
        error_code="D1_CANDIDATES_FAILED",
    )
    decision = policy.evaluate(result)
    assert decision.eligible is False
    assert "D1_CANDIDATES_FAILED" in decision.reason


def test_unrecognized_missing_code_eligible_for_vision() -> None:
    policy = FallbackEligibilityPolicy(enabled=True)
    result = ImageProcessingResult(
        job_id="j",
        asset_id="a",
        status=ImageResultStatus.UNRECOGNIZED,
        processing_mode="CODE_SCAN",
        resolved_by="CODE_SCAN",
        error_code="MISSING_INTERNAL_CODE",
    )
    decision = policy.evaluate(result)
    assert decision.eligible is True
    assert decision.next_strategy == "EXTERNAL_PROVIDER"


def test_dinamic_checksum_never_eligible() -> None:
    policy = FallbackEligibilityPolicy(enabled=True)
    result = ImageProcessingResult(
        job_id="j",
        asset_id="a",
        status=ImageResultStatus.PENDING_MANUAL_REVIEW,
        processing_mode="CODE_SCAN",
        resolved_by="CODE_SCAN",
        error_code="DINAMIC_CHECKSUM_FAILED",
        internal_code="D1BAD",
    )
    decision = policy.evaluate(result)
    assert decision.eligible is False
