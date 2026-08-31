"""PR1 — StructuredPayloadExtractor + deterministic barcode rules."""

from __future__ import annotations

import pytest

from src.application.services.image_processing.extraction_profile_configuration import (
    ExtractionProfileConfigurationError,
    parse_extraction_configuration,
)
from src.application.services.label_validation import (
    LabelValidationContext,
    LabelValidationService,
    StructuredPayloadExtractor,
)
from src.application.services.label_validation.deterministic_config_validation import (
    validate_deterministic_barcode_rules,
)
from src.domain.client_supplier.extraction_profile import (
    CONFIGURATION_SCHEMA_VERSION_V2,
    CaseNormalization,
    CharacterSetPolicy,
    DeterministicBarcodeRules,
    ExtractionProfileConfiguration,
    FieldMappingRule,
    FieldMappingSource,
    PayloadNormalizationRules,
    PayloadStructure,
    QuantityExtractionRules,
)
from src.domain.label_profiles.entities import ResolvedLabelProfile, ResolvedLabelProfiles
from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource
from src.domain.label_validation import (
    CandidateLabel,
    LabelValidationErrorCode,
    LabelValidationStatus,
)


def _profiles(
    *,
    item: LabelProfileSource = LabelProfileSource.SUPPLIER,
    position: LabelProfileSource = LabelProfileSource.SUPPLIER,
) -> ResolvedLabelProfiles:
    return ResolvedLabelProfiles(
        item=ResolvedLabelProfile(
            label_kind=LabelKind.ITEM,
            source=item,
            client_supplier_id="sup-1",
            resolution_source="CLIENT_SUPPLIER",
        ),
        position=ResolvedLabelProfile(
            label_kind=LabelKind.POSITION,
            source=position,
            client_supplier_id="sup-1",
            resolution_source="CLIENT_SUPPLIER",
        ),
    )


def _v2_item(
    *,
    mappings: tuple[FieldMappingRule, ...],
    structure: PayloadStructure = PayloadStructure.SIMPLE,
    delimiter: str | None = None,
    expected_segments: int | None = None,
    prefix: str | None = None,
    suffix: str | None = None,
    exact_length: int | None = None,
    min_length: int | None = None,
    max_length: int | None = None,
    charset: CharacterSetPolicy = CharacterSetPolicy.ANY,
    normalization: PayloadNormalizationRules | None = None,
    required: tuple[str, ...] = ("sku",),
    pattern: str | None = None,
) -> ExtractionProfileConfiguration:
    return ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        required_fields=required,
        custom_payload_pattern=pattern,
        quantity_rules=QuantityExtractionRules(required=False, minimum=1),
        accepted_barcode_formats=("CODE128", "QR"),
        deterministic=DeterministicBarcodeRules(
            expected_prefix=prefix,
            expected_suffix=suffix,
            exact_length=exact_length,
            min_length=min_length,
            max_length=max_length,
            character_set=charset,
            normalization=normalization or PayloadNormalizationRules(),
            payload_structure=structure,
            delimiter=delimiter,
            expected_segment_count=expected_segments,
            field_mappings=mappings,
            use_advanced_pattern=bool(pattern),
        ),
    )


def test_simple_whole_to_label_id_and_sku() -> None:
    cfg = _v2_item(
        mappings=(
            FieldMappingRule("label_id", FieldMappingSource.WHOLE),
            FieldMappingRule("sku", FieldMappingSource.WHOLE),
        )
    )
    out = StructuredPayloadExtractor().extract(
        raw_payload="ABC001",
        configuration=cfg,
        label_kind=LabelKind.ITEM,
        symbology="CODE_128",
    )
    assert out.ok and out.candidate is not None
    assert out.candidate.label_id == "ABC001"
    assert out.candidate.sku == "ABC001"
    assert out.raw_payload == "ABC001"


def test_simple_whole_to_position_id() -> None:
    cfg = ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        required_fields=("position_id",),
        accepted_barcode_formats=("CODE128",),
        deterministic=DeterministicBarcodeRules(
            field_mappings=(FieldMappingRule("position_id", FieldMappingSource.WHOLE),),
        ),
    )
    out = StructuredPayloadExtractor().extract(
        raw_payload="POS-99",
        configuration=cfg,
        label_kind=LabelKind.POSITION,
    )
    assert out.ok and out.candidate is not None
    assert out.candidate.position_id == "POS-99"


def test_prefix_suffix_length_charset() -> None:
    cfg = _v2_item(
        mappings=(FieldMappingRule("sku", FieldMappingSource.WHOLE),),
        prefix="LPN",
        suffix="X",
        exact_length=8,
        charset=CharacterSetPolicy.ALPHANUMERIC,
    )
    svc = LabelValidationService()
    ctx = LabelValidationContext(
        resolved_profiles=_profiles(),
        item_extraction_configuration=cfg,
    )
    ok = svc.validate(
        CandidateLabel(raw_payload="LPN1234X", symbology="CODE_128"),
        context=ctx,
        label_kind=LabelKind.ITEM,
    )
    assert ok.status is LabelValidationStatus.VALID

    bad_prefix = svc.validate(
        CandidateLabel(raw_payload="XXX1234X", symbology="CODE_128"),
        context=ctx,
        label_kind=LabelKind.ITEM,
    )
    assert bad_prefix.error_code == LabelValidationErrorCode.LABEL_PREFIX_MISMATCH.value

    bad_suffix = svc.validate(
        CandidateLabel(raw_payload="LPN1234Z", symbology="CODE_128"),
        context=ctx,
        label_kind=LabelKind.ITEM,
    )
    assert bad_suffix.error_code == LabelValidationErrorCode.LABEL_SUFFIX_MISMATCH.value


def test_contradictory_length_rejected_at_config_time() -> None:
    cfg = _v2_item(
        mappings=(FieldMappingRule("sku", FieldMappingSource.WHOLE),),
        exact_length=10,
        min_length=12,
    )
    with pytest.raises(ExtractionProfileConfigurationError):
        validate_deterministic_barcode_rules(cfg)


def test_normalization_preserves_raw() -> None:
    cfg = _v2_item(
        mappings=(FieldMappingRule("sku", FieldMappingSource.WHOLE),),
        normalization=PayloadNormalizationRules(
            trim_outer_whitespace=True,
            case_normalization=CaseNormalization.UPPER,
            remove_internal_spaces=True,
            remove_hyphens=True,
        ),
    )
    out = StructuredPayloadExtractor().extract(
        raw_payload="  ab-c 1  ",
        configuration=cfg,
        label_kind=LabelKind.ITEM,
    )
    assert out.ok and out.candidate is not None
    assert out.raw_payload == "  ab-c 1  "
    assert out.normalized_payload == "ABC1"
    assert out.candidate.sku == "ABC1"
    assert out.candidate.metadata.get("normalized_payload") == "ABC1"


def test_segmented_item_mapping() -> None:
    cfg = _v2_item(
        structure=PayloadStructure.SEGMENTED,
        delimiter="|",
        expected_segments=3,
        required=("label_id", "sku", "quantity"),
        mappings=(
            FieldMappingRule("label_id", FieldMappingSource.SEGMENT, 0),
            FieldMappingRule("sku", FieldMappingSource.SEGMENT, 1),
            FieldMappingRule("quantity", FieldMappingSource.SEGMENT, 2),
        ),
    )
    svc = LabelValidationService()
    result = svc.validate(
        CandidateLabel(raw_payload="ABC001|SKU123|20", symbology="CODE_128"),
        context=LabelValidationContext(
            resolved_profiles=_profiles(),
            item_extraction_configuration=cfg,
        ),
        label_kind=LabelKind.ITEM,
    )
    assert result.status is LabelValidationStatus.VALID
    assert result.label is not None
    assert result.label.label_id == "ABC001"
    assert result.label.sku == "SKU123"
    assert result.label.quantity == 20


def test_segmented_position_mapping() -> None:
    cfg = ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        required_fields=("position_id",),
        accepted_barcode_formats=("CODE128",),
        deterministic=DeterministicBarcodeRules(
            payload_structure=PayloadStructure.SEGMENTED,
            delimiter="|",
            expected_segment_count=3,
            field_mappings=(
                FieldMappingRule("position_id", FieldMappingSource.SEGMENT, 0),
                FieldMappingRule("pallet", FieldMappingSource.SEGMENT, 1),
                FieldMappingRule("side", FieldMappingSource.SEGMENT, 2),
            ),
        ),
    )
    result = LabelValidationService().validate(
        CandidateLabel(raw_payload="POS001|04|RIGHT", symbology="CODE_128"),
        context=LabelValidationContext(
            resolved_profiles=_profiles(),
            position_extraction_configuration=cfg,
        ),
        label_kind=LabelKind.POSITION,
    )
    assert result.status is LabelValidationStatus.VALID
    assert result.label is not None
    assert result.label.position_id == "POS001"
    assert result.label.pallet == "04"
    assert result.label.side == "RIGHT"


def test_segment_count_mismatch() -> None:
    cfg = _v2_item(
        structure=PayloadStructure.SEGMENTED,
        delimiter="|",
        expected_segments=3,
        mappings=(
            FieldMappingRule("sku", FieldMappingSource.SEGMENT, 0),
            FieldMappingRule("quantity", FieldMappingSource.SEGMENT, 1),
        ),
    )
    out = StructuredPayloadExtractor().extract(
        raw_payload="A|B",
        configuration=cfg,
        label_kind=LabelKind.ITEM,
    )
    assert not out.ok
    assert out.error_code == LabelValidationErrorCode.LABEL_SEGMENT_COUNT_MISMATCH.value


@pytest.mark.parametrize(
    ("charset", "payload", "ok"),
    [
        (CharacterSetPolicy.NUMERIC, "12345", True),
        (CharacterSetPolicy.NUMERIC, "12A45", False),
        (CharacterSetPolicy.ALPHANUMERIC, "Ab12", True),
        (CharacterSetPolicy.ALPHANUMERIC, "Ab-12", False),
        (CharacterSetPolicy.UPPERCASE_ALPHANUMERIC, "AB12", True),
        (CharacterSetPolicy.UPPERCASE_ALPHANUMERIC, "Ab12", False),
        (CharacterSetPolicy.HEX, "a1b2CF", True),
        (CharacterSetPolicy.HEX, "ZZ", False),
        (CharacterSetPolicy.ANY, "A_B-1", True),
    ],
)
def test_charset_policies(
    charset: CharacterSetPolicy, payload: str, ok: bool
) -> None:
    cfg = _v2_item(
        mappings=(FieldMappingRule("sku", FieldMappingSource.WHOLE),),
        charset=charset,
    )
    result = LabelValidationService().validate(
        CandidateLabel(raw_payload=payload, symbology="CODE_128"),
        context=LabelValidationContext(
            resolved_profiles=_profiles(),
            item_extraction_configuration=cfg,
        ),
        label_kind=LabelKind.ITEM,
    )
    if ok:
        assert result.status is LabelValidationStatus.VALID
    else:
        assert result.error_code == LabelValidationErrorCode.LABEL_CHARSET_MISMATCH.value


def test_segmented_invalid_quantity_and_duplicate_mapping() -> None:
    cfg = _v2_item(
        structure=PayloadStructure.SEGMENTED,
        delimiter="|",
        expected_segments=2,
        required=("sku", "quantity"),
        mappings=(
            FieldMappingRule("sku", FieldMappingSource.SEGMENT, 0),
            FieldMappingRule("quantity", FieldMappingSource.SEGMENT, 1),
        ),
    )
    bad_qty = LabelValidationService().validate(
        CandidateLabel(raw_payload="SKU1|0", symbology="CODE_128"),
        context=LabelValidationContext(
            resolved_profiles=_profiles(),
            item_extraction_configuration=cfg,
        ),
        label_kind=LabelKind.ITEM,
    )
    assert bad_qty.status is LabelValidationStatus.INVALID

    with pytest.raises(ExtractionProfileConfigurationError):
        validate_deterministic_barcode_rules(
            _v2_item(
                mappings=(
                    FieldMappingRule("sku", FieldMappingSource.WHOLE),
                    FieldMappingRule("sku", FieldMappingSource.WHOLE),
                )
            )
        )


def test_legacy_config_still_parses_and_extracts() -> None:
    raw = {
        "internal_code_sources": [
            {"field_key": "INTERNAL_CODE", "priority": 1, "enabled": True}
        ],
        "quantity_rules": {"required": False, "minimum": 1, "maximum": 999},
        "accepted_barcode_formats": ["CODE128"],
        "custom_payload_pattern": r"^SUP[0-9]{8}$",
        "required_fields": ["internal_code"],
        "validation_rules": {"code": {"min_length": 1, "max_length": 64}},
    }
    cfg = parse_extraction_configuration(raw)
    assert cfg.custom_payload_pattern == r"^SUP[0-9]{8}$"
    result = LabelValidationService().validate(
        CandidateLabel(raw_payload="SUP12345678", symbology="CODE_128"),
        context=LabelValidationContext(
            resolved_profiles=_profiles(),
            item_extraction_configuration=cfg,
        ),
        label_kind=LabelKind.ITEM,
    )
    assert result.status is LabelValidationStatus.VALID
    assert result.label is not None
    assert result.label.sku == "SUP12345678"


def test_parse_v2_deterministic_roundtrip() -> None:
    raw = {
        "configuration_schema_version": 2,
        "internal_code_sources": [
            {"field_key": "INTERNAL_CODE", "priority": 1, "enabled": True}
        ],
        "quantity_rules": {"required": False, "minimum": 1, "maximum": 999},
        "accepted_barcode_formats": ["CODE128"],
        "required_fields": ["sku", "quantity"],
        "deterministic": {
            "payload_structure": "SEGMENTED",
            "delimiter": "|",
            "expected_segment_count": 3,
            "expected_prefix": "A",
            "character_set": "ALPHANUMERIC",
            "field_mappings": [
                {"target": "label_id", "source": "SEGMENT", "segment_index": 0},
                {"target": "sku", "source": "SEGMENT", "segment_index": 1},
                {"target": "quantity", "source": "SEGMENT", "segment_index": 2},
            ],
            "normalization": {"trim_outer_whitespace": True, "case_normalization": "NONE"},
        },
    }
    cfg = parse_extraction_configuration(raw)
    assert cfg.configuration_schema_version == 2
    assert cfg.deterministic is not None
    assert cfg.deterministic.payload_structure is PayloadStructure.SEGMENTED
    public = cfg.to_public_dict()
    assert "deterministic" in public
    assert "visual_hints" in public
