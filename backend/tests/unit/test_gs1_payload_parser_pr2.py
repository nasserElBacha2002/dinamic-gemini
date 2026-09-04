"""PR2 — GS1 payload parser + StructuredPayloadExtractor GS1 path."""

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
from src.application.services.label_validation.gs1_payload_parser import (
    Gs1PayloadParser,
    gs1_mod10_check_digit,
    verify_gs1_check_digit,
)
from src.application.services.label_validation.profile_example_validation import (
    validate_profile_examples_for_activation,
)
from src.domain.client_supplier.extraction_profile import (
    CONFIGURATION_SCHEMA_VERSION_V2,
    DeterministicBarcodeRules,
    ExtractionProfileConfiguration,
    FieldMappingRule,
    FieldMappingSource,
    ItemLabelSemanticType,
    PayloadExample,
    PayloadStructure,
    QuantityExtractionRules,
    gs1_sscc_template,
)
from src.domain.label_profiles.entities import ResolvedLabelProfile, ResolvedLabelProfiles
from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource
from src.domain.label_validation import (
    CandidateLabel,
    LabelValidationErrorCode,
    LabelValidationStatus,
)

_GS = "\x1d"
_VALID_SSCC = "000123456700000008"
_INVALID_SSCC_CD = "000123456700000009"
_VALID_GTIN14 = "09521234500001"


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
            source=LabelProfileSource.SUPPLIER,
            client_supplier_id="sup-1",
            resolution_source="CLIENT_SUPPLIER",
        ),
    )


def _gs1_sscc_cfg() -> ExtractionProfileConfiguration:
    return ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        semantic_type=ItemLabelSemanticType.SSCC.value,
        required_fields=("label_id",),
        quantity_rules=QuantityExtractionRules(required=False, minimum=1),
        accepted_barcode_formats=("CODE128", "QR"),
        deterministic=DeterministicBarcodeRules(
            payload_structure=PayloadStructure.GS1,
            required_application_identifiers=("00",),
            field_mappings=(
                FieldMappingRule(
                    "label_id",
                    FieldMappingSource.APPLICATION_IDENTIFIER,
                    application_identifier="00",
                ),
            ),
        ),
    )


def test_check_digit_matches_gs1_manual_example() -> None:
    # GS1.org check-digit service / Gen Specs §7.9.1 GTIN-13 example.
    assert gs1_mod10_check_digit("629104150021") == 3
    assert verify_gs1_check_digit(_VALID_SSCC)
    assert not verify_gs1_check_digit(_INVALID_SSCC_CD)


def test_parse_valid_sscc_parenthesized() -> None:
    result = Gs1PayloadParser().parse(f"(00){_VALID_SSCC}")
    assert result.ok
    assert result.by_ai()["00"].normalized_value == _VALID_SSCC


def test_parse_invalid_sscc_length() -> None:
    result = Gs1PayloadParser().parse("(00)12345")
    assert not result.ok
    assert result.error_code == LabelValidationErrorCode.LABEL_GS1_FIELD_INVALID.value


def test_parse_invalid_sscc_check_digit() -> None:
    result = Gs1PayloadParser().parse(f"(00){_INVALID_SSCC_CD}")
    assert not result.ok
    assert result.error_code == LabelValidationErrorCode.LABEL_GS1_CHECK_DIGIT_FAILED.value


def test_parse_valid_gtin() -> None:
    result = Gs1PayloadParser().parse(f"(01){_VALID_GTIN14}")
    assert result.ok
    assert result.by_ai()["01"].normalized_value == _VALID_GTIN14


def test_parse_invalid_gtin_check_digit() -> None:
    bad = _VALID_GTIN14[:-1] + ("0" if _VALID_GTIN14[-1] != "0" else "1")
    result = Gs1PayloadParser().parse(f"(01){bad}")
    assert result.error_code == LabelValidationErrorCode.LABEL_GS1_CHECK_DIGIT_FAILED.value


def test_variable_lot_and_serial_with_gs_separator() -> None:
    payload = f"01{_VALID_GTIN14}10LOT-A{_GS}21SER99"
    result = Gs1PayloadParser().parse(payload)
    assert result.ok
    assert result.by_ai()["10"].normalized_value == "LOT-A"
    assert result.by_ai()["21"].normalized_value == "SER99"


def test_expiration_and_count() -> None:
    result = Gs1PayloadParser().parse(f"(01){_VALID_GTIN14}(17)251231(37)12")
    assert result.ok
    assert result.by_ai()["17"].normalized_value == "2025-12-31"
    assert result.by_ai()["37"].normalized_value == "12"


def test_invalid_expiration_rejected() -> None:
    result = Gs1PayloadParser().parse(f"(01){_VALID_GTIN14}(17)251332")
    assert result.error_code == LabelValidationErrorCode.LABEL_GS1_FIELD_INVALID.value


def test_malformed_ai() -> None:
    result = Gs1PayloadParser().parse("XX123")
    assert result.error_code == LabelValidationErrorCode.LABEL_GS1_INVALID.value


def test_hri_leading_garbage_rejected() -> None:
    result = Gs1PayloadParser().parse(f"ABC(00){_VALID_SSCC}")
    assert not result.ok
    assert result.error_code == LabelValidationErrorCode.LABEL_GS1_INVALID.value


def test_unknown_predefined_ai_preserved() -> None:
    result = Gs1PayloadParser().parse(f"(01){_VALID_GTIN14}(11)250101")
    assert result.ok
    unknown = [f for f in result.fields if f.ai == "11"]
    assert len(unknown) == 1
    assert not unknown[0].known


def test_extractor_sscc_does_not_invent_sku_or_quantity() -> None:
    cfg = _gs1_sscc_cfg()
    out = StructuredPayloadExtractor().extract(
        raw_payload=f"(00){_VALID_SSCC}",
        configuration=cfg,
        label_kind=LabelKind.ITEM,
        symbology="CODE_128",
    )
    assert out.ok and out.candidate is not None
    assert out.candidate.label_id == _VALID_SSCC
    assert out.candidate.sku is None
    assert out.candidate.quantity is None


def test_required_ai_missing() -> None:
    cfg = _gs1_sscc_cfg()
    out = StructuredPayloadExtractor().extract(
        raw_payload=f"(01){_VALID_GTIN14}",
        configuration=cfg,
        label_kind=LabelKind.ITEM,
        symbology="CODE_128",
    )
    assert out.error_code == LabelValidationErrorCode.LABEL_GS1_REQUIRED_AI_MISSING.value


def test_validation_service_sscc_valid() -> None:
    cfg = _gs1_sscc_cfg()
    result = LabelValidationService().validate(
        CandidateLabel(raw_payload=f"(00){_VALID_SSCC}", symbology="CODE_128"),
        context=LabelValidationContext(
            resolved_profiles=_profiles(),
            item_extraction_configuration=cfg,
        ),
        label_kind=LabelKind.ITEM,
    )
    assert result.status is LabelValidationStatus.VALID
    assert result.label is not None
    assert result.label.label_id == _VALID_SSCC
    assert result.label.sku is None
    assert result.label.quantity is None


def test_examples_activation_valid_and_invalid() -> None:
    cfg = gs1_sscc_template()
    validate_profile_examples_for_activation(cfg, label_kind=LabelKind.ITEM)

    bad = ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        semantic_type=ItemLabelSemanticType.SSCC.value,
        required_fields=("label_id",),
        accepted_barcode_formats=("CODE128",),
        deterministic=cfg.deterministic,
        valid_examples=(
            PayloadExample(raw_payload=f"(00){_INVALID_SSCC_CD}", symbology="CODE_128"),
        ),
    )
    with pytest.raises(ExtractionProfileConfigurationError) as exc:
        validate_profile_examples_for_activation(bad, label_kind=LabelKind.ITEM)
    assert exc.value.code == LabelValidationErrorCode.LABEL_PROFILE_EXAMPLE_MISMATCH.value


def test_draft_may_omit_examples_but_gs1_structure_validates() -> None:
    cfg = _gs1_sscc_cfg()
    validate_deterministic_barcode_rules(cfg)
    validate_profile_examples_for_activation(cfg, label_kind=LabelKind.ITEM)


def test_parse_v2_gs1_roundtrip() -> None:
    raw = gs1_sscc_template().to_public_dict()
    cfg = parse_extraction_configuration(raw)
    assert cfg.deterministic is not None
    assert cfg.deterministic.payload_structure is PayloadStructure.GS1
    assert cfg.valid_examples
    assert cfg.invalid_examples
