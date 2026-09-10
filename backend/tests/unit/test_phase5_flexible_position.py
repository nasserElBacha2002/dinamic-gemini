"""Phase 5 flexible position — signature policy, channel gates, shadow, accept."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from src.application.dto.access_principal import AccessPrincipal
from src.application.dto.position_materialization import MaterializePositionCommand
from src.application.services.image_processing.code_scan_label_classifier import (
    CodeScanLabelClassifier,
)
from src.application.services.position_recognition import (
    AcceptPositionCoordinator,
    AcceptPositionRequest,
    CanonicalPositionValidationCommand,
    CanonicalPositionValidator,
    FlexiblePositionChannel,
    FlexibleShadowOutcome,
    PositionCompatibilityPolicy,
    PositionFlexibleShadowEvaluator,
    PositionSignaturePolicy,
    compare_flexible_shadow,
    is_flexible_channel_enabled,
)
from src.application.services.positioning_label_signing import (
    PositioningLabelSigningConfig,
    PositioningLabelSigningService,
)
from src.domain.aisle_location.payload import build_positioning_label_payload
from src.domain.label_validation import CandidateLabel
from src.domain.label_validation.context import LabelValidationContext
from src.domain.position_label_detection.entities import PositionLabelDetectionStatus
from src.domain.position_materialization.entities import (
    MaterializePositionResult,
    PositionMaterializationStatus,
)
from src.domain.position_recognition import (
    CanonicalPositionRecognition,
    CanonicalPositionValidationResult,
    CanonicalPositionValidationStatus,
    PositionRecognitionSource,
    PositionSignatureEvidence,
    PositionSignatureVerification,
)
from src.env_settings.grouped_settings import LimitsAndSchemaSettings
from src.observability.metrics.registry import get_metrics_registry


class StubResolver:
    def __init__(self, status: PositionLabelDetectionStatus) -> None:
        self.status = status

    def resolve(self, *, public_label_id: str, expected_client_id: str):
        from types import SimpleNamespace

        return SimpleNamespace(detection_status=self.status, label=None)


class StubMaterializer:
    def __init__(self, result: MaterializePositionResult) -> None:
        self.result = result
        self.calls = 0

    def execute(self, command: MaterializePositionCommand) -> MaterializePositionResult:
        self.calls += 1
        return self.result


def _signing() -> PositioningLabelSigningService:
    return PositioningLabelSigningService(
        PositioningLabelSigningConfig(secret="test-secret-at-least-16", key_version=1)
    )


def _context(client_id: str = "client-1") -> LabelValidationContext:
    return LabelValidationContext(resolved_profiles=None, client_id=client_id)


def _command(raw: str) -> CanonicalPositionValidationCommand:
    return CanonicalPositionValidationCommand(
        candidate=CandidateLabel(raw_payload=raw, symbology="QR_CODE"),
        source=PositionRecognitionSource.CODE_SCAN,
        context=_context(),
    )


def _unsigned_payload(label_id: str = "POS-OPT-1") -> str:
    return json.dumps(build_positioning_label_payload(public_label_id=label_id))


def _signed_payload(label_id: str = "POS-OPT-1") -> str:
    payload = build_positioning_label_payload(public_label_id=label_id)
    return json.dumps(_signing().sign_payload(payload))


def _legacy_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSITION_FLEXIBLE_VALIDATION_ENABLED", "false")
    monkeypatch.setenv("POSITION_PREEXISTENCE_REQUIRED", "true")
    monkeypatch.setenv("POSITION_AUTO_MATERIALIZATION_ENABLED", "false")
    monkeypatch.setenv("POSITION_IMPORT_MATERIALIZATION_ENABLED", "false")
    monkeypatch.setenv("POSITION_SIGNATURE_POLICY", "REQUIRED")
    monkeypatch.setenv("POSITION_FLEXIBLE_SHADOW_MODE_ENABLED", "false")
    monkeypatch.setenv("POSITION_FLEXIBLE_CODE_SCAN_ENABLED", "false")
    monkeypatch.setenv("POSITION_FLEXIBLE_VISION_ENABLED", "false")
    monkeypatch.setenv("POSITION_FLEXIBLE_MOBILE_ENABLED", "false")
    monkeypatch.setenv("POSITION_FLEXIBLE_IMPORT_ENABLED", "false")
    monkeypatch.setenv("POSITION_FLEXIBLE_REVIEW_ENABLED", "false")


def test_signature_required_missing_rejects_without_unsigned_legacy() -> None:
    result = CanonicalPositionValidator(
        signing=_signing(),
        resolver=StubResolver(PositionLabelDetectionStatus.LABEL_NOT_FOUND),
        policy=PositionCompatibilityPolicy.resolve(
            signature_validation_enabled=True,
            allow_unsigned_legacy=False,
            preexistence_required=True,
            flexible_validation_enabled=False,
            signature_policy=PositionSignaturePolicy.REQUIRED,
        ),
    ).validate(_command(_unsigned_payload()))

    assert result.status is CanonicalPositionValidationStatus.SIGNATURE_REQUIRED_BY_LEGACY_POLICY
    assert result.recognition is not None
    assert result.recognition.signature.verification is PositionSignatureVerification.MISSING


def test_signature_optional_missing_continues_to_unmaterialized() -> None:
    result = CanonicalPositionValidator(
        signing=_signing(),
        resolver=StubResolver(PositionLabelDetectionStatus.LABEL_NOT_FOUND),
        policy=PositionCompatibilityPolicy.resolve(
            signature_validation_enabled=True,
            allow_unsigned_legacy=False,
            preexistence_required=False,
            flexible_validation_enabled=True,
            signature_policy=PositionSignaturePolicy.OPTIONAL,
        ),
    ).validate(_command(_unsigned_payload()))

    assert result.status is CanonicalPositionValidationStatus.VALID_UNMATERIALIZED
    assert result.recognition is not None
    assert result.recognition.signature.verification is PositionSignatureVerification.MISSING
    assert result.recognition.evidence.get("signature_policy") == "OPTIONAL"


def test_signature_optional_invalid_never_equated_with_missing() -> None:
    payload = json.loads(_signed_payload())
    payload["signature"] = "0" * 64
    result = CanonicalPositionValidator(
        signing=_signing(),
        policy=PositionCompatibilityPolicy.resolve(
            signature_validation_enabled=True,
            allow_unsigned_legacy=False,
            preexistence_required=False,
            flexible_validation_enabled=True,
            signature_policy=PositionSignaturePolicy.OPTIONAL,
        ),
    ).validate(_command(json.dumps(payload)))

    assert result.status is CanonicalPositionValidationStatus.INVALID_SIGNATURE
    assert result.recognition is not None
    assert result.recognition.signature.verification is PositionSignatureVerification.INVALID


def test_signature_not_applicable_skips_hmac() -> None:
    result = CanonicalPositionValidator(
        signing=_signing(),
        resolver=StubResolver(PositionLabelDetectionStatus.LABEL_NOT_FOUND),
        policy=PositionCompatibilityPolicy.resolve(
            signature_validation_enabled=True,
            allow_unsigned_legacy=False,
            preexistence_required=False,
            flexible_validation_enabled=True,
            signature_policy=PositionSignaturePolicy.NOT_APPLICABLE,
        ),
    ).validate(_command(_unsigned_payload()))

    assert result.status is CanonicalPositionValidationStatus.VALID_UNMATERIALIZED
    assert result.recognition is not None
    assert (
        result.recognition.signature.verification is PositionSignatureVerification.NOT_APPLICABLE
    )


def test_channel_gate_requires_master_flexible(monkeypatch: pytest.MonkeyPatch) -> None:
    _legacy_defaults(monkeypatch)
    monkeypatch.setenv("POSITION_FLEXIBLE_CODE_SCAN_ENABLED", "true")
    with pytest.raises(ValidationError):
        LimitsAndSchemaSettings()


def test_import_flexible_requires_import_materialization(monkeypatch: pytest.MonkeyPatch) -> None:
    _legacy_defaults(monkeypatch)
    monkeypatch.setenv("POSITION_FLEXIBLE_VALIDATION_ENABLED", "true")
    monkeypatch.setenv("POSITION_PREEXISTENCE_REQUIRED", "false")
    monkeypatch.setenv("POSITION_AUTO_MATERIALIZATION_ENABLED", "true")
    monkeypatch.setenv("POSITION_FLEXIBLE_IMPORT_ENABLED", "true")
    monkeypatch.setenv("POSITION_IMPORT_MATERIALIZATION_ENABLED", "false")
    with pytest.raises(ValidationError):
        LimitsAndSchemaSettings()


def test_is_flexible_channel_enabled_matrix(monkeypatch: pytest.MonkeyPatch) -> None:
    _legacy_defaults(monkeypatch)
    monkeypatch.setenv("POSITION_FLEXIBLE_VALIDATION_ENABLED", "true")
    monkeypatch.setenv("POSITION_PREEXISTENCE_REQUIRED", "false")
    monkeypatch.setenv("POSITION_AUTO_MATERIALIZATION_ENABLED", "true")
    monkeypatch.setenv("POSITION_IMPORT_MATERIALIZATION_ENABLED", "true")
    monkeypatch.setenv("POSITION_FLEXIBLE_CODE_SCAN_ENABLED", "true")
    monkeypatch.setenv("POSITION_FLEXIBLE_IMPORT_ENABLED", "true")
    settings = LimitsAndSchemaSettings()

    assert is_flexible_channel_enabled(settings, FlexiblePositionChannel.CODE_SCAN) is True
    assert is_flexible_channel_enabled(settings, FlexiblePositionChannel.VISION) is False
    assert is_flexible_channel_enabled(settings, FlexiblePositionChannel.IMPORT) is True


def test_phase5_defaults_remain_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    _legacy_defaults(monkeypatch)
    settings = LimitsAndSchemaSettings()
    assert settings.position_flexible_validation_enabled is False
    assert settings.position_preexistence_required is True
    assert settings.position_auto_materialization_enabled is False
    assert settings.position_import_materialization_enabled is False
    assert settings.position_signature_policy == "REQUIRED"
    assert settings.position_flexible_shadow_mode_enabled is False
    assert settings.position_flexible_code_scan_enabled is False
    assert settings.position_flexible_vision_enabled is False
    assert settings.position_flexible_mobile_enabled is False
    assert settings.position_flexible_import_enabled is False
    assert settings.position_flexible_review_enabled is False


def test_shadow_does_not_change_productive_outcome() -> None:
    metrics = get_metrics_registry()
    metrics.reset_for_tests()
    productive_policy = PositionCompatibilityPolicy.resolve(
        signature_validation_enabled=True,
        allow_unsigned_legacy=False,
        preexistence_required=True,
        flexible_validation_enabled=False,
        signature_policy=PositionSignaturePolicy.REQUIRED,
    )
    validator = CanonicalPositionValidator(
        signing=_signing(),
        resolver=StubResolver(PositionLabelDetectionStatus.LABEL_NOT_FOUND),
        policy=productive_policy,
    )
    evaluator = PositionFlexibleShadowEvaluator(enabled=True)
    evaluation = evaluator.evaluate(validator, _command(_signed_payload("POS-SHADOW")))

    assert (
        evaluation.productive.status
        is CanonicalPositionValidationStatus.PREEXISTENCE_REQUIRED_BY_LEGACY_POLICY
    )
    assert evaluation.shadow is not None
    assert evaluation.shadow.status is CanonicalPositionValidationStatus.VALID_UNMATERIALIZED
    assert evaluation.comparison is not None
    assert evaluation.comparison.outcome is FlexibleShadowOutcome.DIVERGENCE_FLEXIBLE_ACCEPTS
    snapshot = metrics.snapshot()
    assert any("position_flexible_evaluation_total" in name for name in snapshot)
    assert any("position_flexible_divergence_total" in name for name in snapshot)


def test_compare_flexible_shadow_match_reject() -> None:
    rejected = CanonicalPositionValidationResult(
        status=CanonicalPositionValidationStatus.INVALID_FORMAT,
        error_code="INVALID_FORMAT",
    )
    comparison = compare_flexible_shadow(rejected, rejected)
    assert comparison.outcome is FlexibleShadowOutcome.MATCH_REJECT
    assert comparison.diverged is False


def test_accept_coordinator_requires_location_when_flexible_auto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _legacy_defaults(monkeypatch)
    monkeypatch.setenv("POSITION_FLEXIBLE_VALIDATION_ENABLED", "true")
    monkeypatch.setenv("POSITION_PREEXISTENCE_REQUIRED", "false")
    monkeypatch.setenv("POSITION_AUTO_MATERIALIZATION_ENABLED", "true")
    monkeypatch.setenv("POSITION_FLEXIBLE_CODE_SCAN_ENABLED", "true")
    settings = LimitsAndSchemaSettings()
    recognition = CanonicalPositionRecognition(
        raw_code="POS-1",
        normalized_code="POS-1",
        source=PositionRecognitionSource.CODE_SCAN,
        signature=PositionSignatureEvidence(
            present=True,
            verification=PositionSignatureVerification.VERIFIED,
        ),
    )
    validation = CanonicalPositionValidationResult(
        status=CanonicalPositionValidationStatus.VALID_UNMATERIALIZED,
        recognition=recognition,
    )
    materializer = StubMaterializer(
        MaterializePositionResult(
            status=PositionMaterializationStatus.MATERIALIZED,
            location_id="loc-1",
        )
    )
    coordinator = AcceptPositionCoordinator(
        settings=settings,
        auto_materialization_enabled=True,
        materializer=materializer,  # type: ignore[arg-type]
    )
    outcome = coordinator.accept(
        AcceptPositionRequest(
            validation=validation,
            channel=FlexiblePositionChannel.CODE_SCAN,
            materialize_command=MaterializePositionCommand(
                recognition=recognition,
                inventory_id="inv-1",
                aisle_id="aisle-1",
                principal=AccessPrincipal(
                    actor_id="actor-1",
                    client_id="client-1",
                    roles=frozenset(),
                    is_platform=False,
                ),
                idempotency_key="k1",
                capture_id="cap-1",
            ),
        )
    )
    assert outcome.accepted is True
    assert outcome.location_id == "loc-1"
    assert materializer.calls == 1


def test_accept_coordinator_rejects_null_location_on_materialize_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _legacy_defaults(monkeypatch)
    monkeypatch.setenv("POSITION_FLEXIBLE_VALIDATION_ENABLED", "true")
    monkeypatch.setenv("POSITION_PREEXISTENCE_REQUIRED", "false")
    monkeypatch.setenv("POSITION_AUTO_MATERIALIZATION_ENABLED", "true")
    monkeypatch.setenv("POSITION_FLEXIBLE_REVIEW_ENABLED", "true")
    settings = LimitsAndSchemaSettings()
    recognition = CanonicalPositionRecognition(
        raw_code="POS-1",
        normalized_code="POS-1",
        source=PositionRecognitionSource.MANUAL,
        signature=PositionSignatureEvidence(
            present=False,
            verification=PositionSignatureVerification.NOT_APPLICABLE,
        ),
    )
    validation = CanonicalPositionValidationResult(
        status=CanonicalPositionValidationStatus.VALID_UNMATERIALIZED,
        recognition=recognition,
    )
    coordinator = AcceptPositionCoordinator(
        settings=settings,
        auto_materialization_enabled=True,
        materializer=StubMaterializer(  # type: ignore[arg-type]
            MaterializePositionResult(
                status=PositionMaterializationStatus.MATERIALIZED,
                location_id=None,
            )
        ),
    )
    outcome = coordinator.accept(
        AcceptPositionRequest(
            validation=validation,
            channel=FlexiblePositionChannel.REVIEW,
            materialize_command=MaterializePositionCommand(
                recognition=recognition,
                inventory_id="inv-1",
                aisle_id="aisle-1",
                principal=AccessPrincipal(
                    actor_id="actor-1",
                    client_id="client-1",
                    roles=frozenset(),
                    is_platform=False,
                ),
                idempotency_key="k2",
                capture_id="cap-1",
            ),
        )
    )
    assert outcome.accepted is False
    assert outcome.error_code == "POSITION_LOCATION_ID_REQUIRED"


def test_ambiguous_code_does_not_become_position() -> None:
    """AMBIGUOUS_CODE from resolver must not be classified as a position."""

    class AmbiguousResolver:
        def resolve(self, *, public_label_id: str, expected_client_id: str):
            from types import SimpleNamespace

            return SimpleNamespace(
                detection_status=PositionLabelDetectionStatus.DUPLICATE_POSITION_CODES,
                label=None,
            )

    result = CanonicalPositionValidator(
        signing=_signing(),
        resolver=AmbiguousResolver(),
        policy=PositionCompatibilityPolicy.resolve(
            signature_validation_enabled=True,
            allow_unsigned_legacy=False,
            preexistence_required=False,
            flexible_validation_enabled=True,
            signature_policy=PositionSignaturePolicy.REQUIRED,
        ),
    ).validate(_command(_signed_payload("POS-DUP")))

    assert result.status is CanonicalPositionValidationStatus.AMBIGUOUS_CODE
    assert result.operationally_accepted is False


def test_code_scan_classifier_ambiguous_precedence_over_position() -> None:
    """LabelValidation AMBIGUOUS is recorded before any position accept path."""
    from src.application.ports.code_scanner import CodeScanDetectionCandidate
    from src.application.services.label_validation import LabelValidationService
    from src.domain.code_scans.entities import CodeType
    from src.domain.label_profiles.entities import ResolvedLabelProfile, ResolvedLabelProfiles
    from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource
    from src.domain.label_validation import LabelValidationResult, LabelValidationStatus

    class AmbiguousValidation(LabelValidationService):
        def validate_best_effort(self, candidate, *, context):
            return LabelValidationResult(
                status=LabelValidationStatus.AMBIGUOUS,
                error_code="AMBIGUOUS_LABEL_KIND",
                detail="both kinds match",
            )

    classifier = CodeScanLabelClassifier(
        validation_service=AmbiguousValidation(),
        canonical_position_validator=CanonicalPositionValidator(),
    )
    profiles = ResolvedLabelProfiles(
        item=ResolvedLabelProfile(
            label_kind=LabelKind.ITEM,
            source=LabelProfileSource.SUPPLIER,
            client_supplier_id="s1",
        ),
        position=ResolvedLabelProfile(
            label_kind=LabelKind.POSITION,
            source=LabelProfileSource.SUPPLIER,
            client_supplier_id="s1",
        ),
    )
    result = classifier.classify(
        [CodeScanDetectionCandidate(code_type=CodeType.QR, code_value="AMBIG-1")],
        context=LabelValidationContext(resolved_profiles=profiles, client_id="client-1"),
    )
    assert result.ambiguous_indexes == (0,)
    assert result.positions == ()
    assert result.items == ()
