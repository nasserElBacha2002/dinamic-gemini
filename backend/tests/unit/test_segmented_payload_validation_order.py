"""SEGMENTED payload: extract/map before identity shape validation (generic)."""

from __future__ import annotations

import pytest

from src.application.services.label_validation import (
    LabelValidationContext,
    LabelValidationService,
    StructuredPayloadExtractor,
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
    QuantityPresence,
    RecognitionMode,
)
from src.domain.label_profiles.entities import ResolvedLabelProfile, ResolvedLabelProfiles
from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource
from src.domain.label_validation import (
    CandidateLabel,
    LabelValidationErrorCode,
    LabelValidationStatus,
)


def _profiles() -> ResolvedLabelProfiles:
    return ResolvedLabelProfiles(
        item=ResolvedLabelProfile(
            label_kind=LabelKind.ITEM,
            source=LabelProfileSource.SUPPLIER,
            client_supplier_id="sup-1",
            resolution_source="CLIENT_SUPPLIER",
            extraction_profile_version=1,
        ),
        position=ResolvedLabelProfile(
            label_kind=LabelKind.POSITION,
            source=LabelProfileSource.SUPPLIER,
            client_supplier_id="sup-1",
            resolution_source="CLIENT_SUPPLIER",
            extraction_profile_version=1,
        ),
    )


def _segmented_item(
    *,
    prefix: str | None = "PRE",
    exact_length: int | None = 10,
    label_idx: int = 0,
    qty_idx: int = 1,
    expected_segments: int = 2,
    delimiter: str = "|",
    quantity_required: bool = True,
    charset: CharacterSetPolicy = CharacterSetPolicy.ALPHANUMERIC_WITH_HYPHEN,
    normalization: PayloadNormalizationRules | None = None,
) -> ExtractionProfileConfiguration:
    return ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        recognition_mode=RecognitionMode.FULL,
        semantic_type="LPN",
        required_fields=("label_id", "quantity") if quantity_required else ("label_id",),
        accepted_barcode_formats=("QR", "CODE128"),
        quantity_rules=QuantityExtractionRules(
            required=quantity_required,
            minimum=1,
            maximum=99_999_999,
            allow_decimals=False,
            allow_negative=False,
            expected_presence=(
                QuantityPresence.ALWAYS if quantity_required else QuantityPresence.OPTIONAL
            ),
            allow_external_fallback=False,
        ),
        deterministic=DeterministicBarcodeRules(
            expected_prefix=prefix,
            exact_length=exact_length,
            character_set=charset,
            normalization=normalization
            or PayloadNormalizationRules(
                trim_outer_whitespace=True,
                case_normalization=CaseNormalization.UPPER,
                remove_internal_spaces=True,
                remove_hyphens=False,
            ),
            payload_structure=PayloadStructure.SEGMENTED,
            delimiter=delimiter,
            expected_segment_count=expected_segments,
            field_mappings=(
                FieldMappingRule("label_id", FieldMappingSource.SEGMENT, label_idx),
                FieldMappingRule("quantity", FieldMappingSource.SEGMENT, qty_idx),
            ),
        ),
    )


def _validate(payload: str, cfg: ExtractionProfileConfiguration):
    return LabelValidationService().validate(
        CandidateLabel(raw_payload=payload, symbology="QR"),
        context=LabelValidationContext(
            resolved_profiles=_profiles(),
            item_extraction_configuration=cfg,
        ),
        label_kind=LabelKind.ITEM,
    )


def test_segmented_happy_path_identity_length_excludes_quantity() -> None:
    cfg = _segmented_item(prefix="ASI", exact_length=10)
    result = _validate("ASI-9T6R2V|48", cfg)
    assert result.status is LabelValidationStatus.VALID
    assert result.error_code is None
    assert result.label is not None
    assert result.label.label_id == "ASI-9T6R2V"
    assert result.label.quantity == 48
    assert (result.diagnostics or {}).get("segment_count") == "2"
    assert (result.diagnostics or {}).get("payload_structure") == "SEGMENTED"
    assert "label_id" in str((result.diagnostics or {}).get("mapped_fields") or "")


@pytest.mark.parametrize(
    ("payload", "label_id", "qty"),
    [
        ("ASI-7K2M9Q|24", "ASI-7K2M9Q", 24),
        ("ASI-4F8N3C|12", "ASI-4F8N3C", 12),
        ("ASI-9T6R2V|48", "ASI-9T6R2V", 48),
        ("ASI-2W5H8D|6", "ASI-2W5H8D", 6),
    ],
)
def test_segmented_valid_quantities(payload: str, label_id: str, qty: int) -> None:
    result = _validate(payload, _segmented_item(prefix="ASI", exact_length=10))
    assert result.status is LabelValidationStatus.VALID
    assert result.label is not None
    assert result.label.label_id == label_id
    assert result.label.quantity == qty


def test_segmented_label_id_length_nine_rejected() -> None:
    result = _validate("ASI-9T6R2|48", _segmented_item(prefix="ASI", exact_length=10))
    assert result.status is LabelValidationStatus.INVALID
    assert result.error_code == LabelValidationErrorCode.LABEL_LENGTH_MISMATCH.value
    assert (result.diagnostics or {}).get("failed_field") == "label_id"
    assert (result.diagnostics or {}).get("length", {}).get("found") == 9


def test_segmented_label_id_length_eleven_rejected() -> None:
    result = _validate("ASI-9T6R2VX|48", _segmented_item(prefix="ASI", exact_length=10))
    assert result.status is LabelValidationStatus.INVALID
    assert result.error_code == LabelValidationErrorCode.LABEL_LENGTH_MISMATCH.value
    assert (result.diagnostics or {}).get("length", {}).get("found") == 11


def test_segmented_quantity_suffix_does_not_inflate_length() -> None:
    """Regression: full payload ASI-9T6R2V|48 has len 13; identity is 10."""
    result = _validate("ASI-9T6R2V|48", _segmented_item(prefix="ASI", exact_length=10))
    assert result.status is LabelValidationStatus.VALID
    assert result.error_code != LabelValidationErrorCode.LABEL_LENGTH_MISMATCH.value


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ("ASI-9T6R2V48", LabelValidationErrorCode.LABEL_SEGMENT_COUNT_MISMATCH.value),
        ("ASI-9T6R2V", LabelValidationErrorCode.LABEL_SEGMENT_COUNT_MISMATCH.value),
        ("ASI-9T6R2V|48|X", LabelValidationErrorCode.LABEL_SEGMENT_COUNT_MISMATCH.value),
        ("ASI-9T6R2V||48", LabelValidationErrorCode.LABEL_SEGMENT_COUNT_MISMATCH.value),
        ("ASI-9T6R2V|", LabelValidationErrorCode.LABEL_REQUIRED_FIELD_MISSING.value),
        ("|48", LabelValidationErrorCode.LABEL_REQUIRED_FIELD_MISSING.value),
    ],
)
def test_segmented_structural_errors(payload: str, code: str) -> None:
    result = _validate(payload, _segmented_item(prefix="ASI", exact_length=10))
    assert result.status is LabelValidationStatus.INVALID
    assert result.error_code == code


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ("ASI-9T6R2V|abc", LabelValidationErrorCode.LABEL_FIELD_INVALID.value),
        ("ASI-9T6R2V|12.5", LabelValidationErrorCode.LABEL_FIELD_INVALID.value),
        ("ASI-9T6R2V|-3", LabelValidationErrorCode.LABEL_FIELD_INVALID.value),
        ("ASI-9T6R2V|0", LabelValidationErrorCode.LABEL_FIELD_INVALID.value),
    ],
)
def test_segmented_quantity_invalid(payload: str, code: str) -> None:
    result = _validate(payload, _segmented_item(prefix="ASI", exact_length=10))
    assert result.status is LabelValidationStatus.INVALID
    assert result.error_code == code


def test_segmented_quantity_optional_via_simple_identity() -> None:
    cfg = ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        recognition_mode=RecognitionMode.MINIMAL,
        required_fields=("label_id",),
        accepted_barcode_formats=("QR",),
        quantity_rules=QuantityExtractionRules(
            required=False,
            expected_presence=QuantityPresence.OPTIONAL,
            allow_external_fallback=False,
        ),
        deterministic=DeterministicBarcodeRules(
            expected_prefix="ASI",
            exact_length=10,
            character_set=CharacterSetPolicy.ALPHANUMERIC_WITH_HYPHEN,
            payload_structure=PayloadStructure.SIMPLE,
            field_mappings=(FieldMappingRule("label_id", FieldMappingSource.WHOLE),),
        ),
    )
    result = _validate("ASI-9T6R2V", cfg)
    assert result.status is LabelValidationStatus.VALID
    assert result.label is not None
    assert result.label.quantity is None


def test_segmented_quantity_required_unmapped() -> None:
    cfg = ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        required_fields=("label_id", "quantity"),
        accepted_barcode_formats=("QR",),
        quantity_rules=QuantityExtractionRules(
            required=True,
            expected_presence=QuantityPresence.ALWAYS,
            allow_external_fallback=False,
        ),
        deterministic=DeterministicBarcodeRules(
            expected_prefix="ASI",
            exact_length=10,
            character_set=CharacterSetPolicy.ALPHANUMERIC_WITH_HYPHEN,
            payload_structure=PayloadStructure.SEGMENTED,
            delimiter="|",
            expected_segment_count=1,
            field_mappings=(FieldMappingRule("label_id", FieldMappingSource.SEGMENT, 0),),
        ),
    )
    result = _validate("ASI-9T6R2V", cfg)
    assert result.status is LabelValidationStatus.INVALID
    assert result.error_code == LabelValidationErrorCode.LABEL_REQUIRED_FIELD_MISSING.value


def test_segmented_normalization_preserves_delimiter_and_quantity() -> None:
    cfg = _segmented_item(
        prefix="ASI",
        exact_length=10,
        normalization=PayloadNormalizationRules(
            trim_outer_whitespace=True,
            case_normalization=CaseNormalization.UPPER,
            remove_internal_spaces=True,
            remove_hyphens=False,
        ),
    )
    result = _validate("  asi-9t6r2v|48  ", cfg)
    assert result.status is LabelValidationStatus.VALID
    assert result.label is not None
    assert result.label.label_id == "ASI-9T6R2V"
    assert result.label.quantity == 48


def test_segmented_remove_hyphens_applies_only_to_label_id() -> None:
    cfg = _segmented_item(
        prefix="ASI",
        exact_length=9,
        normalization=PayloadNormalizationRules(
            trim_outer_whitespace=True,
            case_normalization=CaseNormalization.UPPER,
            remove_internal_spaces=False,
            remove_hyphens=True,
        ),
    )
    result = _validate("ASI-9T6R2V|48", cfg)
    assert result.status is LabelValidationStatus.VALID
    assert result.label is not None
    assert result.label.label_id == "ASI9T6R2V"
    assert result.label.quantity == 48


def test_segmented_reversed_mapping_order() -> None:
    cfg = _segmented_item(prefix="ASI", exact_length=10, label_idx=1, qty_idx=0)
    result = _validate("48|ASI-9T6R2V", cfg)
    assert result.status is LabelValidationStatus.VALID
    assert result.label is not None
    assert result.label.label_id == "ASI-9T6R2V"
    assert result.label.quantity == 48


def test_segmented_index_out_of_range() -> None:
    cfg = _segmented_item(prefix="ASI", exact_length=10, label_idx=0, qty_idx=5)
    result = _validate("ASI-9T6R2V|48", cfg)
    assert result.status is LabelValidationStatus.INVALID
    assert result.error_code == LabelValidationErrorCode.LABEL_SEGMENT_COUNT_MISMATCH.value


def test_segmented_prefix_mismatch_on_label_id_only() -> None:
    result = _validate("XXX-9T6R2V|48", _segmented_item(prefix="ASI", exact_length=10))
    assert result.status is LabelValidationStatus.INVALID
    assert result.error_code == LabelValidationErrorCode.LABEL_PREFIX_MISMATCH.value
    assert (result.diagnostics or {}).get("failed_field") == "label_id"


def test_simple_still_validates_whole_payload_length() -> None:
    cfg = ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        required_fields=("label_id",),
        accepted_barcode_formats=("QR",),
        quantity_rules=QuantityExtractionRules(
            required=False,
            expected_presence=QuantityPresence.OPTIONAL,
            allow_external_fallback=False,
        ),
        deterministic=DeterministicBarcodeRules(
            expected_prefix="ASI",
            exact_length=10,
            character_set=CharacterSetPolicy.ALPHANUMERIC_WITH_HYPHEN,
            payload_structure=PayloadStructure.SIMPLE,
            field_mappings=(FieldMappingRule("label_id", FieldMappingSource.WHOLE),),
        ),
    )
    bad = _validate("ASI-9T6R2V|48", cfg)
    assert bad.status is LabelValidationStatus.INVALID
    assert bad.error_code == LabelValidationErrorCode.LABEL_LENGTH_MISMATCH.value
    good = _validate("ASI-9T6R2V", cfg)
    assert good.status is LabelValidationStatus.VALID


def test_extractor_segment_metadata() -> None:
    cfg = _segmented_item(prefix="ASI", exact_length=10)
    out = StructuredPayloadExtractor().extract(
        raw_payload="ASI-9T6R2V|48",
        configuration=cfg,
        label_kind=LabelKind.ITEM,
    )
    assert out.ok and out.candidate is not None
    assert out.candidate.label_id == "ASI-9T6R2V"
    assert out.candidate.quantity == 48
    assert out.candidate.metadata.get("segment_count") == "2"
    assert out.candidate.metadata.get("delimiter_detected") == "true"
