"""Dual-kind diagnostics and SIMPLE POSITION classification (generic profiles only)."""

from __future__ import annotations

from src.application.services.label_validation.label_validation_service import (
    LabelValidationService,
)
from src.domain.client_supplier.extraction_profile import (
    CharacterSetPolicy,
    minimal_supplier_item_configuration,
    minimal_supplier_position_configuration,
)
from src.domain.label_profiles.entities import ResolvedLabelProfile, ResolvedLabelProfiles
from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource
from src.domain.label_validation import (
    CandidateLabel,
    LabelValidationErrorCode,
    LabelValidationStatus,
)
from src.domain.label_validation.context import LabelValidationContext


def _ctx(*, item_cfg, position_cfg) -> LabelValidationContext:
    return LabelValidationContext(
        resolved_profiles=ResolvedLabelProfiles(
            item=ResolvedLabelProfile(
                label_kind=LabelKind.ITEM,
                source=LabelProfileSource.SUPPLIER,
                client_supplier_id="fixture-supplier",
                resolution_source="CLIENT_SUPPLIER",
            ),
            position=ResolvedLabelProfile(
                label_kind=LabelKind.POSITION,
                source=LabelProfileSource.SUPPLIER,
                client_supplier_id="fixture-supplier",
                resolution_source="CLIENT_SUPPLIER",
            ),
        ),
        item_extraction_configuration=item_cfg,
        position_extraction_configuration=position_cfg,
    )


def test_simple_position_valid_when_item_prefix_mismatches() -> None:
    item = minimal_supplier_item_configuration(
        expected_prefix="PRD", exact_length=10, character_set=CharacterSetPolicy.ALPHANUMERIC_WITH_HYPHEN
    )
    position = minimal_supplier_position_configuration(
        expected_prefix="LOC", exact_length=10, character_set=CharacterSetPolicy.ALPHANUMERIC_WITH_HYPHEN
    )
    svc = LabelValidationService()
    result = svc.validate_best_effort(
        CandidateLabel(raw_payload="LOC-A01-02", symbology="QR_CODE"),
        context=_ctx(item_cfg=item, position_cfg=position),
    )
    assert result.status is LabelValidationStatus.VALID
    assert result.label_kind is LabelKind.POSITION
    assert result.diagnostics["selected_kind"] == "POSITION"
    assert result.diagnostics["item_validation"]["status"] == "INVALID"
    assert result.diagnostics["position_validation"]["status"] == "VALID"
    assert result.diagnostics["item_validation"]["error_code"] == (
        LabelValidationErrorCode.LABEL_PREFIX_MISMATCH.value
    )


def test_both_invalid_prefers_structural_over_prefix() -> None:
    """POSITION SEGMENTED mismatch must not be hidden by ITEM PREFIX mismatch."""
    item = minimal_supplier_item_configuration(
        expected_prefix="PRD", exact_length=10, character_set=CharacterSetPolicy.ALPHANUMERIC_WITH_HYPHEN
    )
    # Intentionally SEGMENTED so a SIMPLE location identity fails structurally.
    from src.domain.client_supplier.extraction_profile import (
        DeterministicBarcodeRules,
        FieldMappingRule,
        FieldMappingSource,
        PayloadNormalizationRules,
        PayloadStructure,
        CaseNormalization,
        ExtractionProfileConfiguration,
        RecognitionMode,
        CONFIGURATION_SCHEMA_VERSION_V2,
        PositionLabelSemanticType,
        QuantityExtractionRules,
        FieldDataType,
        QuantityPresence,
        MissingQuantityAction,
    )

    position = ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        recognition_mode=RecognitionMode.FULL,
        semantic_type=PositionLabelSemanticType.LOCATION.value,
        quantity_rules=QuantityExtractionRules(
            required=False,
            data_type=FieldDataType.INTEGER,
            expected_presence=QuantityPresence.OPTIONAL,
            missing_quantity_action=MissingQuantityAction.PENDING_MANUAL_REVIEW,
            allow_external_fallback=False,
            aliases=(),
            allowed_spatial_relations=(),
        ),
        required_fields=("position_id",),
        deterministic=DeterministicBarcodeRules(
            expected_prefix="LOC",
            exact_length=None,
            character_set=CharacterSetPolicy.ALPHANUMERIC_WITH_HYPHEN,
            normalization=PayloadNormalizationRules(
                trim_outer_whitespace=True,
                case_normalization=CaseNormalization.UPPER,
                remove_internal_spaces=True,
                remove_hyphens=False,
            ),
            payload_structure=PayloadStructure.SEGMENTED,
            delimiter="|",
            expected_segment_count=4,
            field_mappings=(
                FieldMappingRule(
                    target="position_id", source=FieldMappingSource.SEGMENT, segment_index=0
                ),
            ),
        ),
        accepted_barcode_formats=("QR", "CODE128"),
    )
    svc = LabelValidationService()
    result = svc.validate_best_effort(
        CandidateLabel(raw_payload="LOC-A01-02", symbology="CODE_128"),
        context=_ctx(item_cfg=item, position_cfg=position),
    )
    assert result.status is LabelValidationStatus.INVALID
    assert "item_validation" in result.diagnostics
    assert "position_validation" in result.diagnostics
    assert result.diagnostics["item_validation"]["error_code"] == (
        LabelValidationErrorCode.LABEL_PREFIX_MISMATCH.value
    )
    assert result.diagnostics["position_validation"]["error_code"] == (
        LabelValidationErrorCode.LABEL_SEGMENT_COUNT_MISMATCH.value
    )
    # Top-level must surface the structural POSITION failure, not ITEM PREFIX alone.
    assert result.error_code == LabelValidationErrorCode.LABEL_SEGMENT_COUNT_MISMATCH.value


def test_evaluation_order_does_not_change_selected_kind() -> None:
    item = minimal_supplier_item_configuration(
        expected_prefix="PRD", exact_length=10, character_set=CharacterSetPolicy.ALPHANUMERIC_WITH_HYPHEN
    )
    position = minimal_supplier_position_configuration(
        expected_prefix="LOC", exact_length=10, character_set=CharacterSetPolicy.ALPHANUMERIC_WITH_HYPHEN
    )
    svc = LabelValidationService()
    ctx = _ctx(item_cfg=item, position_cfg=position)
    item_hit = svc.validate_best_effort(
        CandidateLabel(raw_payload="PRD-123456", symbology="QR_CODE"), context=ctx
    )
    pos_hit = svc.validate_best_effort(
        CandidateLabel(raw_payload="LOC-A01-02", symbology="QR_CODE"), context=ctx
    )
    assert item_hit.label_kind is LabelKind.ITEM
    assert pos_hit.label_kind is LabelKind.POSITION
    # Same payload evaluated twice remains stable (no order-dependent flip).
    again = svc.validate_best_effort(
        CandidateLabel(raw_payload="LOC-A01-02", symbology="CODE_128"), context=ctx
    )
    assert again.label_kind is LabelKind.POSITION
    assert again.diagnostics["selected_kind"] == "POSITION"
