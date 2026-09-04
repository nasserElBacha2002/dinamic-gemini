"""MINIMAL recognition mode — identity via prefix + length + charset + target."""

from __future__ import annotations

from src.application.ports.external_image_analysis_provider import (
    ExternalAnalysisResult,
    ExternalAnalysisStatus,
)
from src.application.services.image_processing.vision_candidate_bridge import (
    normalize_vision_via_label_validation,
)
from src.application.services.label_validation import LabelValidationService
from src.domain.client_supplier.extraction_profile import (
    CharacterSetPolicy,
    ItemLabelSemanticType,
    default_extraction_configuration,
    minimal_supplier_item_configuration,
    minimal_supplier_position_configuration,
)
from src.domain.image_processing.contracts import ImageResultStatus
from src.domain.label_profiles.entities import ResolvedLabelProfile, ResolvedLabelProfiles
from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource
from src.domain.label_validation import (
    CandidateLabel,
    LabelValidationErrorCode,
    LabelValidationStatus,
    RecognitionSource,
)
from src.domain.label_validation.context import LabelValidationContext


def _item_profiles() -> ResolvedLabelProfiles:
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


def _position_profiles() -> ResolvedLabelProfiles:
    return ResolvedLabelProfiles(
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


def test_minimal_item_lpna_valid_without_sku_or_quantity() -> None:
    cfg = minimal_supplier_item_configuration(
        expected_prefix="LPNA",
        exact_length=10,
        character_set=CharacterSetPolicy.UPPERCASE_ALPHANUMERIC,
        semantic_type=ItemLabelSemanticType.LPN.value,
    )
    assert cfg.is_minimal()
    svc = LabelValidationService()
    result = svc.validate(
        CandidateLabel(
            raw_payload="LPNA000184",
            recognition_source=RecognitionSource.VISION,
            label_kind_hint=LabelKind.ITEM,
            label_id="LPNA000184",
        ),
        context=LabelValidationContext(
            resolved_profiles=_item_profiles(),
            item_extraction_configuration=cfg,
        ),
        label_kind=LabelKind.ITEM,
    )
    assert result.status is LabelValidationStatus.VALID
    assert result.label is not None
    assert result.label.label_id == "LPNA000184"
    assert result.label.sku is None
    assert result.label.quantity is None
    assert result.diagnostics.get("identity_valid") is True


def test_minimal_item_prefix_fail() -> None:
    cfg = minimal_supplier_item_configuration(expected_prefix="LPNA", exact_length=10)
    result = LabelValidationService().validate(
        CandidateLabel(
            raw_payload="XXXX000184",
            recognition_source=RecognitionSource.VISION,
            label_id="XXXX000184",
            symbology="QR",
        ),
        context=LabelValidationContext(
            resolved_profiles=_item_profiles(),
            item_extraction_configuration=cfg,
        ),
        label_kind=LabelKind.ITEM,
    )
    assert result.status is LabelValidationStatus.INVALID
    assert result.error_code == LabelValidationErrorCode.LABEL_PREFIX_MISMATCH.value
    assert result.diagnostics["prefix"]["pass"] is False


def test_minimal_item_length_fail() -> None:
    cfg = minimal_supplier_item_configuration(expected_prefix="LPNA", exact_length=10)
    result = LabelValidationService().validate(
        CandidateLabel(
            raw_payload="LPNA00018",
            recognition_source=RecognitionSource.VISION,
            label_id="LPNA00018",
            symbology="QR",
        ),
        context=LabelValidationContext(
            resolved_profiles=_item_profiles(),
            item_extraction_configuration=cfg,
        ),
        label_kind=LabelKind.ITEM,
    )
    assert result.status is LabelValidationStatus.INVALID
    assert result.error_code == LabelValidationErrorCode.LABEL_LENGTH_MISMATCH.value
    assert result.diagnostics["length"]["pass"] is False
    assert result.diagnostics["length"]["found"] == 9


def test_minimal_item_charset_fail() -> None:
    cfg = minimal_supplier_item_configuration(
        expected_prefix="LPNA",
        exact_length=10,
        character_set=CharacterSetPolicy.UPPERCASE_ALPHANUMERIC,
    )
    result = LabelValidationService().validate(
        CandidateLabel(
            raw_payload="LPNA00018-",
            recognition_source=RecognitionSource.VISION,
            label_id="LPNA00018-",
            symbology="QR",
        ),
        context=LabelValidationContext(
            resolved_profiles=_item_profiles(),
            item_extraction_configuration=cfg,
        ),
        label_kind=LabelKind.ITEM,
    )
    assert result.status is LabelValidationStatus.INVALID
    assert result.error_code == LabelValidationErrorCode.LABEL_CHARSET_MISMATCH.value


def test_minimal_position_a04_valid() -> None:
    cfg = minimal_supplier_position_configuration(
        expected_prefix="A",
        exact_length=8,
        character_set=CharacterSetPolicy.ALPHANUMERIC_WITH_HYPHEN,
    )
    result = LabelValidationService().validate(
        CandidateLabel(
            raw_payload="A04-R-02",
            recognition_source=RecognitionSource.VISION,
            label_kind_hint=LabelKind.POSITION,
            position_id="A04-R-02",
        ),
        context=LabelValidationContext(
            resolved_profiles=_position_profiles(),
            position_extraction_configuration=cfg,
        ),
        label_kind=LabelKind.POSITION,
    )
    assert result.status is LabelValidationStatus.VALID
    assert result.label is not None
    assert result.label.position_id == "A04-R-02"
    assert result.label.pallet is None
    assert result.label.side is None
    assert result.label.level is None


def test_legacy_default_profile_still_requires_internal_code_path() -> None:
    """schema v1 / FULL default keeps legacy required_fields behavior."""
    cfg = default_extraction_configuration()
    assert not cfg.is_minimal()
    assert "internal_code" in cfg.required_fields or "quantity" in cfg.required_fields


def test_vision_candidate_minimal_item_resolves_external() -> None:
    cfg = minimal_supplier_item_configuration(expected_prefix="LPNA", exact_length=10)
    ctx = LabelValidationContext(
        resolved_profiles=_item_profiles(),
        item_extraction_configuration=cfg,
        job_id="job-1",
    )
    analysis = ExternalAnalysisResult(
        status=ExternalAnalysisStatus.VALID,
        provider_name="gemini",
        model_name="x",
        normalized_result={"label_kind": "ITEM", "label_id": "LPNA000184"},
        duration_ms=5,
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
    assert out.resolved_by == "EXTERNAL_PROVIDER"
    assert out.internal_code == "LPNA000184"
    assert out.product_results
    assert out.product_results[0].label_id == "LPNA000184"
    assert out.product_results[0].internal_code is None
    assert out.product_results[0].quantity is None
    assert out.evidence.get("identity_valid") is True


def test_vision_candidate_minimal_position_resolves() -> None:
    cfg = minimal_supplier_position_configuration(expected_prefix="A", exact_length=8)
    ctx = LabelValidationContext(
        resolved_profiles=_position_profiles(),
        position_extraction_configuration=cfg,
        job_id="job-1",
    )
    analysis = ExternalAnalysisResult(
        status=ExternalAnalysisStatus.VALID,
        provider_name="gemini",
        model_name="x",
        normalized_result={"label_kind": "POSITION", "position_id": "A04-R-02"},
        duration_ms=5,
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
    assert out.resolved_by == "EXTERNAL_PROVIDER"
    pos = (out.evidence or {}).get("position_label_detection") or {}
    assert pos.get("position_id") == "A04-R-02"
