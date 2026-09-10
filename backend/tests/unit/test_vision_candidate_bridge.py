"""Vision → CandidateLabel → LabelValidationService bridge (final phase)."""

from __future__ import annotations

import json

import pytest

from src.application.ports.external_image_analysis_provider import (
    ExternalAnalysisResult,
    ExternalAnalysisStatus,
)
from src.application.services.image_processing.fallback_eligibility_policy import (
    FallbackEligibilityPolicy,
)
from src.application.services.image_processing.vision_candidate_bridge import (
    VISION_POSITION_RAW_EVIDENCE_REQUIRED,
    candidate_from_vision_analysis,
    normalize_vision_via_label_validation,
)
from src.application.services.label_validation import LabelValidationService
from src.application.services.position_recognition import CanonicalPositionValidator
from src.application.services.positioning_label_signing import (
    PositioningLabelSigningConfig,
    PositioningLabelSigningService,
)
from src.domain.aisle_location.payload import build_positioning_label_payload
from src.domain.client_supplier.extraction_profile import (
    CONFIGURATION_SCHEMA_VERSION_V2,
    DeterministicBarcodeRules,
    ExtractionProfileConfiguration,
    FieldMappingRule,
    FieldMappingSource,
    ItemLabelSemanticType,
    PayloadStructure,
    PositionLabelSemanticType,
    QuantityExtractionRules,
)
from src.domain.image_processing.contracts import ImageProcessingResult, ImageResultStatus
from src.domain.label_profiles.entities import ResolvedLabelProfile, ResolvedLabelProfiles
from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource
from src.domain.label_validation import RecognitionSource
from src.domain.label_validation.context import LabelValidationContext
from src.observability.metrics.instruments import VISION_CANDIDATE_TOTAL
from src.observability.metrics.registry import get_metrics_registry


@pytest.fixture(autouse=True)
def _reset_metrics_registry() -> None:
    get_metrics_registry().reset_for_tests()
    yield
    get_metrics_registry().reset_for_tests()


class CountingLabelValidationService(LabelValidationService):
    def __init__(self) -> None:
        super().__init__()
        self.best_effort_calls = 0
        self.validate_calls = 0

    def validate(self, candidate, *, context, label_kind):
        self.validate_calls += 1
        return super().validate(candidate, context=context, label_kind=label_kind)

    def validate_best_effort(self, candidate, *, context):
        self.best_effort_calls += 1
        return super().validate_best_effort(candidate, context=context)


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
    assert cand.metadata["raw_evidence_source"] == "raw_payload"


def test_no_candidate_records_exact_bounded_metric_without_identifiers() -> None:
    out = normalize_vision_via_label_validation(
        job_id="job-secret-1",
        asset_id="asset-secret-1",
        analysis=ExternalAnalysisResult(
            status=ExternalAnalysisStatus.VALID,
            provider_name="provider-secret",
            model_name="model-secret",
        ),
        validation_context=LabelValidationContext(
            resolved_profiles=None,
            client_id="client-secret-1",
        ),
        base_fields={},
        evidence={},
    )

    assert out.status is ImageResultStatus.UNRECOGNIZED
    labels = {
        "component": "candidate",
        "mode": "UNKNOWN",
        "outcome": "no_candidate",
    }
    registry = get_metrics_registry()
    assert registry.get_counter_value(VISION_CANDIDATE_TOTAL, labels) == 1.0
    rendered = registry.render_prometheus()
    assert (
        'vision_candidate_total{component="candidate",mode="UNKNOWN",'
        'outcome="no_candidate"} 1.0' in rendered
    )
    for forbidden in (
        "job-secret-1",
        "asset-secret-1",
        "client-secret-1",
        "provider-secret",
        "model-secret",
    ):
        assert forbidden not in rendered


def test_structured_only_position_fails_closed_without_typed_raw_evidence(caplog) -> None:
    inferred = "INFERRED-POSITION-SECRET"
    analysis = ExternalAnalysisResult(
        status=ExternalAnalysisStatus.VALID,
        provider_name="gemini",
        model_name="x",
        normalized_result={
            "position_id": inferred,
            "pallet": "04",
            "side": "RIGHT",
            "level": "02",
        },
    )

    candidate = candidate_from_vision_analysis(analysis)
    assert candidate is not None
    assert candidate.raw_payload == ""
    assert candidate.metadata["raw_evidence_source"] == ""

    out = normalize_vision_via_label_validation(
        job_id="job-1",
        asset_id="asset-1",
        analysis=analysis,
        validation_context=LabelValidationContext(
            resolved_profiles=None,
            client_id="client-1",
        ),
        base_fields={},
        evidence={},
    )

    assert out.status is ImageResultStatus.PENDING_MANUAL_REVIEW
    assert out.error_code == VISION_POSITION_RAW_EVIDENCE_REQUIRED
    assert out.validation_errors == [VISION_POSITION_RAW_EVIDENCE_REQUIRED]
    assert out.vision_position_evidence == ()
    assert "raw_payload_hash" not in repr(out.evidence)
    assert inferred not in repr(out.evidence)
    assert inferred not in caplog.text
    assert (
        get_metrics_registry().get_counter_value(
            VISION_CANDIDATE_TOTAL,
            {
                "component": "validation",
                "mode": "POSITION",
                "outcome": "raw_evidence_required",
            },
        )
        == 1.0
    )


def test_item_internal_code_legacy_candidate_is_not_exact_raw_evidence() -> None:
    analysis = ExternalAnalysisResult(
        status=ExternalAnalysisStatus.VALID,
        provider_name="gemini",
        model_name="x",
        internal_code="SKU-LEGACY-1",
        quantity=2,
    )

    candidate = candidate_from_vision_analysis(analysis, label_kind_hint=LabelKind.ITEM)

    assert candidate is not None
    assert candidate.raw_payload == "SKU-LEGACY-1"
    assert candidate.sku is None
    assert candidate.metadata["raw_evidence_source"] == ""


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
        normalized_result={"raw_payload": "LPNA000184|SKU773421|24"},
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
    assert out.product_results[0].label_id == "LPNA000184"
    assert out.product_results[0].internal_code == "SKU773421"
    assert out.product_results[0].quantity == 24
    assert out.resolved_by == "EXTERNAL_PROVIDER"
    assert out.evidence.get("vision_unified_validation") is True
    assert (
        get_metrics_registry().get_counter_value(
            VISION_CANDIDATE_TOTAL,
            {
                "component": "bridge",
                "mode": "ITEM",
                "outcome": "resolved",
            },
        )
        == 1.0
    )


def test_vision_position_segmented_via_label_validation() -> None:
    cfg = ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        semantic_type=PositionLabelSemanticType.AISLE_POSITION.value,
        required_fields=("position_id", "pallet", "side", "level"),
        accepted_barcode_formats=("CODE128",),
        quantity_rules=QuantityExtractionRules(required=False),
        deterministic=DeterministicBarcodeRules(
            payload_structure=PayloadStructure.SEGMENTED,
            delimiter="|",
            expected_segment_count=4,
            field_mappings=(
                FieldMappingRule("position_id", FieldMappingSource.SEGMENT, segment_index=0),
                FieldMappingRule("pallet", FieldMappingSource.SEGMENT, segment_index=1),
                FieldMappingRule("side", FieldMappingSource.SEGMENT, segment_index=2),
                FieldMappingRule("level", FieldMappingSource.SEGMENT, segment_index=3),
            ),
        ),
    )
    profiles = ResolvedLabelProfiles(
        item=ResolvedLabelProfile(
            label_kind=LabelKind.ITEM,
            source=LabelProfileSource.DINAMIC,
            client_supplier_id=None,
            resolution_source="DINAMIC",
        ),
        position=ResolvedLabelProfile(
            label_kind=LabelKind.POSITION,
            source=LabelProfileSource.SUPPLIER,
            client_supplier_id="sup-1",
            resolution_source="CLIENT_SUPPLIER",
        ),
    )
    ctx = LabelValidationContext(
        resolved_profiles=profiles,
        position_extraction_configuration=cfg,
        job_id="job-1",
        client_id="client-1",
    )
    analysis = ExternalAnalysisResult(
        status=ExternalAnalysisStatus.VALID,
        provider_name="gemini",
        model_name="x",
        # Hint POSITION so bridge does not default to ITEM; fields still come from raw.
        normalized_result={
            "raw_payload": "a04-r-02|04|right|02",
            "position_id": "a04-r-02",
        },
        duration_ms=8,
    )
    validation = CountingLabelValidationService()
    out = normalize_vision_via_label_validation(
        job_id="job-1",
        asset_id="a1",
        analysis=analysis,
        validation_context=ctx,
        base_fields={},
        evidence={},
        label_validation_service=validation,
        canonical_position_validator=CanonicalPositionValidator(
            label_validator=validation,
        ),
    )
    assert out.status is ImageResultStatus.RESOLVED_EXTERNAL
    assert out.resolved_by == "EXTERNAL_PROVIDER"
    assert (out.evidence or {}).get("result_kind") == "POSITION_ONLY"
    pos = (out.evidence or {}).get("position_label_detection") or {}
    assert pos.get("position_id") == "A04-R-02"
    assert str(pos.get("pallet")) in ("04", "4")
    assert str(pos.get("side")).upper() == "RIGHT"
    assert str(pos.get("level")) in ("02", "2")
    assert validation.validate_calls == 1
    assert validation.best_effort_calls == 0
    typed = out.vision_position_evidence[0]
    assert typed.recognition.raw_code == "a04-r-02|04|right|02"
    assert typed.recognition.normalized_code == "A04-R-02"

    second_analysis = ExternalAnalysisResult(
        status=ExternalAnalysisStatus.VALID,
        provider_name="gemini",
        model_name="x",
        normalized_result={
            "raw_payload": "A04-R-02|04|RIGHT|02",
            "position_id": "A04-R-02",
        },
        duration_ms=8,
    )
    second = normalize_vision_via_label_validation(
        job_id="job-1",
        asset_id="a2",
        analysis=second_analysis,
        validation_context=ctx,
        base_fields={},
        evidence={},
        canonical_position_validator=CanonicalPositionValidator(),
    )
    second_typed = second.vision_position_evidence[0]
    assert second_typed.recognition.normalized_code == typed.recognition.normalized_code
    assert second_typed.raw_evidence.payload_hash != typed.raw_evidence.payload_hash


def test_vision_dinamic_position_with_unverified_signature_is_rejected() -> None:
    payload = build_positioning_label_payload(
        public_label_id="POS-VISION-1",
        key_version=1,
        signature="0" * 64,
    )
    analysis = ExternalAnalysisResult(
        status=ExternalAnalysisStatus.VALID,
        provider_name="gemini",
        model_name="x",
        normalized_result={
            "raw_payload": json.dumps(payload),
            "position_id": "POS-VISION-1",
        },
    )
    validator = CanonicalPositionValidator(
        signing=PositioningLabelSigningService(
            PositioningLabelSigningConfig(
                secret="test-secret-at-least-16",
                key_version=1,
            )
        )
    )

    out = normalize_vision_via_label_validation(
        job_id="job-1",
        asset_id="a1",
        analysis=analysis,
        validation_context=LabelValidationContext(
            resolved_profiles=_profiles(),
            client_id="client-1",
        ),
        base_fields={},
        evidence={},
        canonical_position_validator=validator,
    )

    assert out.status is ImageResultStatus.PENDING_MANUAL_REVIEW
    assert out.error_code == "INVALID_SIGNATURE"


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
