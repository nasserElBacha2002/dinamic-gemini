"""Unit tests — LabelValidationService (Dinamic + Supplier CODE_SCAN rules)."""

from __future__ import annotations

from src.application.services.label_validation import (
    LabelValidationContext,
    LabelValidationService,
    compile_payload_pattern,
)
from src.domain.client_supplier.extraction_profile import (
    CodeValidationRules,
    ExtractionProfileConfiguration,
    ExtractionValidationRules,
    QuantityExtractionRules,
)
from src.domain.label_profiles.entities import (
    ResolvedLabelProfile,
    ResolvedLabelProfiles,
)
from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource
from src.domain.label_validation import (
    CandidateLabel,
    LabelValidationErrorCode,
    LabelValidationStatus,
    RecognitionSource,
)
from src.domain.product_labels.format import (
    build_product_label_payload,
    generate_product_label_id,
)


def _profiles(
    *,
    item: LabelProfileSource = LabelProfileSource.DINAMIC,
    position: LabelProfileSource = LabelProfileSource.DINAMIC,
) -> ResolvedLabelProfiles:
    return ResolvedLabelProfiles(
        item=ResolvedLabelProfile(
            label_kind=LabelKind.ITEM,
            source=item,
            client_supplier_id="sup-1",
            resolution_source="CLIENT_SUPPLIER" if item is LabelProfileSource.SUPPLIER else "DEFAULT",
        ),
        position=ResolvedLabelProfile(
            label_kind=LabelKind.POSITION,
            source=position,
            client_supplier_id="sup-1",
            resolution_source=(
                "CLIENT_SUPPLIER" if position is LabelProfileSource.SUPPLIER else "DEFAULT"
            ),
        ),
    )


def _supplier_item_config(*, pattern: str = r"^SUP[0-9]{8}$") -> ExtractionProfileConfiguration:
    return ExtractionProfileConfiguration(
        accepted_barcode_formats=("CODE128", "QR"),
        custom_payload_pattern=pattern,
        required_fields=("internal_code",),
        validation_rules=ExtractionValidationRules(
            code=CodeValidationRules(min_length=1, max_length=64),
        ),
        quantity_rules=QuantityExtractionRules(required=False),
    )


def test_dinamic_d1_valid() -> None:
    label_id = generate_product_label_id()
    payload = build_product_label_payload(
        label_id=label_id, internal_code="SKU1", quantity=2
    )
    svc = LabelValidationService()
    result = svc.validate(
        CandidateLabel(raw_payload=payload, recognition_source=RecognitionSource.CODE_SCAN),
        context=LabelValidationContext(resolved_profiles=_profiles()),
        label_kind=LabelKind.ITEM,
    )
    assert result.status is LabelValidationStatus.VALID
    assert result.label is not None
    assert result.label.sku == "SKU1"
    assert result.label.quantity == 2


def test_dinamic_d1_invalid_checksum_fail_closed() -> None:
    label_id = generate_product_label_id()
    payload = build_product_label_payload(
        label_id=label_id, internal_code="SKU1", quantity=2
    )
    bad = payload[:-1] + ("0" if payload[-1] != "0" else "1")
    svc = LabelValidationService()
    result = svc.validate(
        CandidateLabel(raw_payload=bad),
        context=LabelValidationContext(resolved_profiles=_profiles()),
        label_kind=LabelKind.ITEM,
    )
    assert result.status is LabelValidationStatus.INVALID
    assert result.error_code == LabelValidationErrorCode.DINAMIC_CHECKSUM_FAILED.value


def test_invalid_d1_not_reinterpreted_as_supplier() -> None:
    label_id = generate_product_label_id()
    payload = build_product_label_payload(
        label_id=label_id, internal_code="SKU1", quantity=2
    )
    bad = payload[:-1] + ("0" if payload[-1] != "0" else "1")
    svc = LabelValidationService()
    result = svc.validate(
        CandidateLabel(raw_payload=bad, symbology="CODE_128"),
        context=LabelValidationContext(
            resolved_profiles=_profiles(item=LabelProfileSource.SUPPLIER),
            item_extraction_configuration=_supplier_item_config(pattern=r"^D1\|.*$"),
        ),
        label_kind=LabelKind.ITEM,
    )
    assert result.status is LabelValidationStatus.INVALID
    assert result.error_code == LabelValidationErrorCode.DINAMIC_CHECKSUM_FAILED.value


def test_supplier_item_valid_pattern() -> None:
    svc = LabelValidationService()
    result = svc.validate(
        CandidateLabel(raw_payload="SUP12345678", symbology="CODE_128"),
        context=LabelValidationContext(
            resolved_profiles=_profiles(item=LabelProfileSource.SUPPLIER),
            item_extraction_configuration=_supplier_item_config(),
        ),
        label_kind=LabelKind.ITEM,
    )
    assert result.status is LabelValidationStatus.VALID
    assert result.label is not None
    assert result.label.sku == "SUP12345678"


def test_supplier_item_invalid_prefix() -> None:
    svc = LabelValidationService()
    result = svc.validate(
        CandidateLabel(raw_payload="XXX12345678", symbology="CODE_128"),
        context=LabelValidationContext(
            resolved_profiles=_profiles(item=LabelProfileSource.SUPPLIER),
            item_extraction_configuration=_supplier_item_config(),
        ),
        label_kind=LabelKind.ITEM,
    )
    assert result.status is LabelValidationStatus.INVALID
    assert result.error_code == LabelValidationErrorCode.LABEL_PATTERN_MISMATCH.value


def test_supplier_item_wrong_symbology() -> None:
    svc = LabelValidationService()
    result = svc.validate(
        CandidateLabel(raw_payload="SUP12345678", symbology="EAN_13"),
        context=LabelValidationContext(
            resolved_profiles=_profiles(item=LabelProfileSource.SUPPLIER),
            item_extraction_configuration=_supplier_item_config(),
        ),
        label_kind=LabelKind.ITEM,
    )
    assert result.status is LabelValidationStatus.INVALID
    assert result.error_code == LabelValidationErrorCode.LABEL_SYMBOLOGY_REJECTED.value


def test_supplier_position_valid() -> None:
    config = ExtractionProfileConfiguration(
        accepted_barcode_formats=("QR",),
        custom_payload_pattern=r"^POS-[A-Z0-9]+$",
        required_fields=(),
    )
    svc = LabelValidationService()
    result = svc.validate(
        CandidateLabel(raw_payload="POS-ABC123", symbology="QR_CODE"),
        context=LabelValidationContext(
            resolved_profiles=_profiles(position=LabelProfileSource.SUPPLIER),
            position_extraction_configuration=config,
        ),
        label_kind=LabelKind.POSITION,
    )
    assert result.status is LabelValidationStatus.VALID
    assert result.label is not None
    assert result.label.position_id == "POS-ABC123"


def test_ambiguous_when_both_kinds_valid() -> None:
    item_cfg = _supplier_item_config(pattern=r"^X[0-9]{3}$")
    pos_cfg = ExtractionProfileConfiguration(
        accepted_barcode_formats=("CODE128",),
        custom_payload_pattern=r"^X[0-9]{3}$",
        required_fields=(),
    )
    svc = LabelValidationService()
    result = svc.validate_best_effort(
        CandidateLabel(raw_payload="X123", symbology="CODE_128"),
        context=LabelValidationContext(
            resolved_profiles=_profiles(
                item=LabelProfileSource.SUPPLIER,
                position=LabelProfileSource.SUPPLIER,
            ),
            item_extraction_configuration=item_cfg,
            position_extraction_configuration=pos_cfg,
        ),
    )
    assert result.status is LabelValidationStatus.AMBIGUOUS
    assert result.error_code == LabelValidationErrorCode.AMBIGUOUS_LABEL_KIND.value


def test_compile_payload_pattern_rejects_invalid() -> None:
    import pytest

    with pytest.raises(Exception):
        compile_payload_pattern("(")
