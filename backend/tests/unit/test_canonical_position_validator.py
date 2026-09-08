from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from src.application.ports.code_scanner import CodeScanDetectionCandidate
from src.application.services.image_processing.code_scan_label_classifier import (
    CodeScanLabelClassifier,
)
from src.application.services.position_recognition import (
    CanonicalPositionValidationCommand,
    CanonicalPositionValidator,
    PositionCodeNormalizationError,
    PositionCompatibilityPolicy,
    normalize_position_code,
)
from src.application.services.positioning_label_signing import (
    PositioningLabelSigningConfig,
    PositioningLabelSigningService,
)
from src.domain.aisle_location.payload import build_positioning_label_payload
from src.domain.client_supplier.extraction_profile import (
    ChecksumPolicy,
    CodeValidationRules,
    ExtractionProfileConfiguration,
    ExtractionValidationRules,
    QuantityExtractionRules,
    minimal_supplier_position_configuration,
)
from src.domain.code_scans.entities import CodeType
from src.domain.label_profiles.entities import ResolvedLabelProfile, ResolvedLabelProfiles
from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource
from src.domain.label_validation import CandidateLabel
from src.domain.label_validation.context import LabelValidationContext
from src.domain.position_label_detection.entities import PositionLabelDetectionStatus
from src.domain.position_recognition import (
    CanonicalPositionValidationStatus,
    PositionRecognitionSource,
    PositionSignatureVerification,
)


class StubResolver:
    def __init__(self, status: PositionLabelDetectionStatus) -> None:
        self.status = status
        self.public_identifiers: list[str] = []

    def resolve(self, *, public_label_id: str, expected_client_id: str):
        self.public_identifiers.append(public_label_id)
        label = (
            SimpleNamespace(id="label-db-1", public_identifier=public_label_id)
            if self.status is PositionLabelDetectionStatus.VALID
            else None
        )
        return SimpleNamespace(detection_status=self.status, label=label)


def _profiles(
    *,
    item: LabelProfileSource = LabelProfileSource.DINAMIC,
    position: LabelProfileSource = LabelProfileSource.DINAMIC,
    supplier_id: str = "supplier-1",
) -> ResolvedLabelProfiles:
    return ResolvedLabelProfiles(
        item=ResolvedLabelProfile(
            label_kind=LabelKind.ITEM,
            source=item,
            client_supplier_id=supplier_id,
        ),
        position=ResolvedLabelProfile(
            label_kind=LabelKind.POSITION,
            source=position,
            client_supplier_id=supplier_id,
            extraction_profile_id="profile-1",
            extraction_profile_version=3,
        ),
    )


def _context(
    *,
    profiles: ResolvedLabelProfiles | None = None,
    position_config: ExtractionProfileConfiguration | None = None,
    item_config: ExtractionProfileConfiguration | None = None,
    client_id: str = "client-1",
) -> LabelValidationContext:
    return LabelValidationContext(
        resolved_profiles=profiles or _profiles(),
        position_extraction_configuration=position_config,
        item_extraction_configuration=item_config,
        client_id=client_id,
    )


def _command(
    raw: str,
    *,
    source: PositionRecognitionSource = PositionRecognitionSource.CODE_SCAN,
    context: LabelValidationContext | None = None,
) -> CanonicalPositionValidationCommand:
    return CanonicalPositionValidationCommand(
        candidate=CandidateLabel(raw_payload=raw, symbology="QR_CODE"),
        source=source,
        context=context or _context(),
    )


def _signing() -> PositioningLabelSigningService:
    return PositioningLabelSigningService(
        PositioningLabelSigningConfig(secret="test-secret-at-least-16", key_version=1)
    )


def _signed_payload() -> str:
    payload = build_positioning_label_payload(
        public_label_id="POS-0001",
        pallet="A-01",
        side="LEFT",
        level=1,
        marker_index=1,
        marker_total=2,
    )
    return json.dumps(_signing().sign_payload(payload))


def _supplier_context(
    *,
    position_config: ExtractionProfileConfiguration | None = None,
    item_config: ExtractionProfileConfiguration | None = None,
) -> LabelValidationContext:
    return _context(
        profiles=_profiles(position=LabelProfileSource.SUPPLIER),
        position_config=position_config or minimal_supplier_position_configuration(),
        item_config=item_config,
    )


def test_signed_dinamic_position_is_valid_existing() -> None:
    result = CanonicalPositionValidator(
        signing=_signing(),
        resolver=StubResolver(PositionLabelDetectionStatus.VALID),
    ).validate(_command(_signed_payload()))

    assert result.status is CanonicalPositionValidationStatus.VALID_EXISTING
    assert result.existing_position_label_id == "label-db-1"
    assert result.recognition is not None
    assert result.recognition.signature.verification is PositionSignatureVerification.VERIFIED


def test_present_but_invalid_signature_is_not_treated_as_verified() -> None:
    payload = json.loads(_signed_payload())
    payload["signature"] = "0" * 64
    result = CanonicalPositionValidator(signing=_signing()).validate(_command(json.dumps(payload)))

    assert result.status is CanonicalPositionValidationStatus.INVALID_SIGNATURE
    assert result.recognition is not None
    assert result.recognition.signature.present is True
    assert result.recognition.signature.verified is False


def test_supplier_position_without_signature_is_valid_unmaterialized() -> None:
    result = CanonicalPositionValidator().validate(
        _command("pos-a-01", context=_supplier_context())
    )

    assert result.status is CanonicalPositionValidationStatus.VALID_UNMATERIALIZED
    assert result.recognition is not None
    assert result.recognition.normalized_code == "POS-A-01"
    assert result.recognition.profile_id == "profile-1"
    assert result.recognition.profile_version == 3


def test_unknown_dinamic_position_can_be_represented_when_policy_allows_it() -> None:
    unsigned = json.dumps(build_positioning_label_payload(public_label_id="POS-UNKNOWN"))
    validator = CanonicalPositionValidator(
        resolver=StubResolver(PositionLabelDetectionStatus.LABEL_NOT_FOUND),
        policy=PositionCompatibilityPolicy.resolve(
            signature_required=False,
            preexistence_required=False,
            flexible_validation_enabled=True,
        ),
    )

    result = validator.validate(_command(unsigned))

    assert result.status is CanonicalPositionValidationStatus.VALID_UNMATERIALIZED
    assert result.structurally_valid is True


def test_invalid_position_format_is_rejected() -> None:
    result = CanonicalPositionValidator().validate(_command("not-a-position"))
    assert result.status is CanonicalPositionValidationStatus.INVALID_FORMAT


def test_ambiguous_item_and_position_code_is_explicit() -> None:
    item_config = ExtractionProfileConfiguration(
        custom_payload_pattern=r"^X[0-9]{3}$",
        required_fields=("internal_code",),
        validation_rules=ExtractionValidationRules(
            code=CodeValidationRules(min_length=1, max_length=64),
        ),
        quantity_rules=QuantityExtractionRules(required=False),
    )
    position_config = ExtractionProfileConfiguration(
        custom_payload_pattern=r"^X[0-9]{3}$",
        required_fields=(),
    )
    context = _context(
        profiles=_profiles(
            item=LabelProfileSource.SUPPLIER,
            position=LabelProfileSource.SUPPLIER,
        ),
        position_config=position_config,
        item_config=item_config,
    )
    result = CanonicalPositionValidator().validate(_command("X123", context=context))
    assert result.status is CanonicalPositionValidationStatus.AMBIGUOUS_CODE


def test_missing_supplier_position_profile_is_not_accepted() -> None:
    context = _context(profiles=_profiles(position=LabelProfileSource.SUPPLIER))
    result = CanonicalPositionValidator().validate(_command("POS-1", context=context))
    assert result.status is CanonicalPositionValidationStatus.PROFILE_NOT_ALLOWED


def test_exact_canonical_maximum_is_accepted() -> None:
    result = CanonicalPositionValidator().validate(_command("A" * 64, context=_supplier_context()))
    assert result.status is CanonicalPositionValidationStatus.VALID_UNMATERIALIZED


def test_over_canonical_maximum_is_rejected_without_truncation() -> None:
    result = CanonicalPositionValidator().validate(_command("A" * 65, context=_supplier_context()))
    assert result.status is CanonicalPositionValidationStatus.FIELD_CONSTRAINT_VIOLATION
    assert result.error_code == "POSITION_CODE_TOO_LONG"


def test_canonical_normalization_is_source_independent() -> None:
    assert normalize_position_code("  a-é/01  ").normalized_code == "A-É/01"


def test_control_characters_are_rejected() -> None:
    with pytest.raises(PositionCodeNormalizationError) as exc:
        normalize_position_code("A-01\nB")
    assert exc.value.code == "POSITION_CODE_CONTROL_CHARACTER"


def test_checksum_failure_remains_distinct_from_format() -> None:
    base = minimal_supplier_position_configuration()
    assert base.deterministic is not None
    config = replace(
        base,
        deterministic=replace(
            base.deterministic,
            checksum_policy=ChecksumPolicy.EAN_GTIN,
        ),
    )
    result = CanonicalPositionValidator().validate(
        _command("1234567890123", context=_supplier_context(position_config=config))
    )
    assert result.status is CanonicalPositionValidationStatus.INVALID_CHECKSUM


def test_code_scan_and_vision_have_same_semantic_outcome() -> None:
    validator = CanonicalPositionValidator()
    context = _supplier_context()
    scan = validator.validate(
        _command("POS-A1", source=PositionRecognitionSource.CODE_SCAN, context=context)
    )
    vision = validator.validate(
        _command("POS-A1", source=PositionRecognitionSource.VISION, context=context)
    )
    assert scan.status is vision.status
    assert scan.recognition is not None and vision.recognition is not None
    assert scan.recognition.normalized_code == vision.recognition.normalized_code


def test_txt_and_api_have_same_semantic_outcome() -> None:
    validator = CanonicalPositionValidator()
    context = _supplier_context()
    txt = validator.validate(
        _command("POS-A1", source=PositionRecognitionSource.TXT, context=context)
    )
    api = validator.validate(
        _command("POS-A1", source=PositionRecognitionSource.API, context=context)
    )
    assert txt.status is api.status
    assert txt.recognition is not None and api.recognition is not None
    assert txt.recognition.normalized_code == api.recognition.normalized_code


def test_legacy_signature_policy_rejection_is_not_structural_invalidity() -> None:
    unsigned = json.dumps(build_positioning_label_payload(public_label_id="POS-UNSIGNED"))
    result = CanonicalPositionValidator().validate(_command(unsigned))

    assert result.status is CanonicalPositionValidationStatus.SIGNATURE_REQUIRED_BY_LEGACY_POLICY
    assert result.structurally_valid is True
    assert result.policy_rejection is True


def test_cross_client_resolution_is_rejected_without_exposing_label() -> None:
    result = CanonicalPositionValidator(
        signing=_signing(),
        resolver=StubResolver(PositionLabelDetectionStatus.CLIENT_MISMATCH),
    ).validate(_command(_signed_payload()))

    assert result.status is CanonicalPositionValidationStatus.PROFILE_NOT_ALLOWED
    assert result.existing_position_label_id is None
    assert result.error_code == "POSITION_SCOPE_MISMATCH"


def test_supplier_scope_must_match_resolved_profile() -> None:
    command = replace(
        _command("POS-A1", context=_supplier_context()),
        client_supplier_id="supplier-other",
    )
    result = CanonicalPositionValidator().validate(command)

    assert result.status is CanonicalPositionValidationStatus.PROFILE_NOT_ALLOWED
    assert result.error_code == "POSITION_SUPPLIER_SCOPE_MISMATCH"


def test_code_scan_resolves_signed_dinamic_identifier_without_case_rewrite() -> None:
    signer = _signing()
    resolver = StubResolver(PositionLabelDetectionStatus.VALID)
    raw = json.dumps(
        signer.sign_payload(build_positioning_label_payload(public_label_id="pos_MixedCase"))
    )
    classifier = CodeScanLabelClassifier(
        canonical_position_validator=CanonicalPositionValidator(
            signing=signer,
            resolver=resolver,
        )
    )

    result = classifier.classify(
        [
            CodeScanDetectionCandidate(
                code_type=CodeType.QR,
                code_value=raw,
            )
        ],
        context=_context(),
    )

    assert len(result.positions) == 1
    assert resolver.public_identifiers == ["pos_MixedCase"]
