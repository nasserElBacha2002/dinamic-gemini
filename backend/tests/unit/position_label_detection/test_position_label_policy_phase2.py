"""Phase 2 — position label signing policy, anti-downgrade, and feature flag."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from src.application.services.position_label_detection.code_classifier import CodeClassifier
from src.application.services.position_label_detection.payload_parser import (
    PositionLabelPayloadParser,
)
from src.application.services.position_label_detection.position_label_policy import (
    PositionLabelPolicyDecision,
    PositionLabelPolicyService,
)
from src.application.services.position_label_detection.resolver import PositionLabelResolver
from src.application.services.position_label_detection.validation_service import (
    PositionLabelValidationService,
)
from src.application.services.position_reconciliation.transitions import (
    resolve_position_transition,
)
from src.application.services.positioning_label_signing import (
    PositioningLabelSigningConfig,
    PositioningLabelSigningService,
)
from src.application.use_cases.position_label_detection.detect_image_position_labels import (
    ImagePositionDetectionCommand,
    ImagePositionDetectionUseCase,
)
from src.domain.aisle_location.payload import build_positioning_label_payload
from src.domain.client_position_label.entities import (
    ClientPositionLabel,
    ClientPositionLabelSignatureStatus,
    ClientPositionLabelStatus,
)
from src.domain.position_label_detection.entities import (
    DetectedCode,
    ImagePositionLabelDetection,
    PositionLabelDetectionStatus,
    PositionLabelSignatureStatus,
)
from src.domain.position_reconciliation.entities import PositionTransitionAction
from src.infrastructure.repositories.memory_client_position_label_repository import (
    MemoryClientPositionLabelRepository,
)
from src.infrastructure.repositories.memory_image_position_label_detection_repository import (
    MemoryImagePositionLabelDetectionRepository,
)


class _Clock:
    def now(self) -> datetime:
        return datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def _signing(
    *,
    secret: str = "test-secret-16chars",
    key_version: int = 1,
    previous: tuple[tuple[int, str], ...] = (),
) -> PositioningLabelSigningService:
    return PositioningLabelSigningService(
        PositioningLabelSigningConfig(
            secret=secret,
            key_version=key_version,
            previous_secrets=previous,
            required=True,
        )
    )


def _use_case(
    *,
    labels: MemoryClientPositionLabelRepository,
    signing: PositioningLabelSigningService | None = None,
    allow_unsigned_legacy: bool = True,
) -> ImagePositionDetectionUseCase:
    signing_svc = signing or _signing()
    resolver = PositionLabelResolver(label_repo=labels)
    return ImagePositionDetectionUseCase(
        classifier=CodeClassifier(max_payload_bytes=4096),
        parser=PositionLabelPayloadParser(max_payload_bytes=4096),
        validator=PositionLabelValidationService(
            signing=signing_svc, signature_validation_enabled=True
        ),
        resolver=resolver,
        policy=PositionLabelPolicyService(
            resolver=resolver,
            allow_unsigned_legacy=allow_unsigned_legacy,
        ),
        repo=MemoryImagePositionLabelDetectionRepository(),
        clock=_Clock(),
        detection_enabled=True,
        persistence_enabled=False,
        max_codes_per_image=16,
    )


def _save_label(
    repo: MemoryClientPositionLabelRepository,
    *,
    public_id: str,
    client_id: str = "client-1",
    payload: dict,
    signature_status: ClientPositionLabelSignatureStatus = ClientPositionLabelSignatureStatus.SIGNED,
    status: ClientPositionLabelStatus = ClientPositionLabelStatus.ACTIVE,
) -> None:
    now = datetime(2026, 8, 28, tzinfo=timezone.utc)
    repo.save(
        ClientPositionLabel(
            id=str(uuid4()),
            client_id=client_id,
            public_identifier=public_id,
            name=public_id,
            normalized_name=public_id.upper(),
            status=status,
            payload_version=int(payload.get("version") or 1),
            canonical_payload=payload,
            created_at=now,
            updated_at=now,
            signature_status=signature_status,
        )
    )


def _run(
    use_case: ImagePositionDetectionUseCase,
    raw: str,
    *,
    client_id: str = "client-1",
) -> ImagePositionLabelDetection:
    result = use_case.execute(
        ImagePositionDetectionCommand(
            client_id=client_id,
            inventory_id="inv-1",
            job_id="job-1",
            source_asset_id="asset-1",
            codes=[DetectedCode(symbology="QR_CODE", raw_value=raw, normalized_value=raw)],
        )
    )
    assert len(result.detections) == 1
    det = result.detections[0]
    assert isinstance(det, ImagePositionLabelDetection)
    return det


def test_signed_valid_resolves_with_accept_policy() -> None:
    labels = MemoryClientPositionLabelRepository()
    signing = _signing()
    payload = signing.sign_payload(
        build_positioning_label_payload(public_label_id="pos_signed", version=1)
    )
    _save_label(labels, public_id="pos_signed", payload=payload)
    det = _run(_use_case(labels=labels, signing=signing), json.dumps(payload, separators=(",", ":")))
    assert det.detection_status is PositionLabelDetectionStatus.VALID
    assert det.signature_status is PositionLabelSignatureStatus.VALID
    assert det.metadata_json.get("policy_decision") == PositionLabelPolicyDecision.ACCEPT.value
    assert det.public_identifier == "pos_signed"


def test_invalid_signature_rejects_no_legacy_fallback() -> None:
    labels = MemoryClientPositionLabelRepository()
    signing = _signing()
    payload = signing.sign_payload(
        build_positioning_label_payload(public_label_id="pos_bad_sig", version=1)
    )
    _save_label(labels, public_id="pos_bad_sig", payload=payload)
    payload["signature"] = "0" * 64
    det = _run(_use_case(labels=labels, signing=signing), json.dumps(payload, separators=(",", ":")))
    assert det.detection_status is PositionLabelDetectionStatus.INVALID_SIGNATURE
    assert det.metadata_json.get("policy_decision") == PositionLabelPolicyDecision.REJECT.value
    assert det.position_label_id is None


def test_v2_signature_removed_is_missing_not_legacy() -> None:
    labels = MemoryClientPositionLabelRepository()
    signing = _signing()
    payload = build_positioning_label_payload(
        public_label_id="pos_v2_strip",
        pallet="01",
        side="LEFT",
        level=1,
        marker_index=1,
        marker_total=1,
    )
    signed = signing.sign_payload(payload)
    _save_label(
        labels,
        public_id="pos_v2_strip",
        payload=signed,
        signature_status=ClientPositionLabelSignatureStatus.UNSIGNED,
    )
    unsigned_raw = json.dumps(payload, separators=(",", ":"))
    det = _run(_use_case(labels=labels, signing=signing), unsigned_raw)
    assert det.detection_status is PositionLabelDetectionStatus.MISSING_SIGNATURE
    assert det.metadata_json.get("policy_decision") == PositionLabelPolicyDecision.REJECT.value


def test_v2_invalid_signature_never_legacy() -> None:
    labels = MemoryClientPositionLabelRepository()
    signing = _signing()
    payload = build_positioning_label_payload(
        public_label_id="pos_v2_bad",
        pallet="01",
        side="RIGHT",
        level=2,
        marker_index=1,
        marker_total=1,
    )
    signed = signing.sign_payload(payload)
    _save_label(labels, public_id="pos_v2_bad", payload=signed)
    signed["signature"] = "f" * 64
    det = _run(_use_case(labels=labels, signing=signing), json.dumps(signed, separators=(",", ":")))
    assert det.detection_status is PositionLabelDetectionStatus.INVALID_SIGNATURE
    assert det.metadata_json.get("policy_decision") == PositionLabelPolicyDecision.REJECT.value


def test_unknown_key_version_rejects() -> None:
    labels = MemoryClientPositionLabelRepository()
    signing = _signing(key_version=1)
    payload = signing.sign_payload(
        build_positioning_label_payload(public_label_id="pos_old_key", version=1)
    )
    payload["key_version"] = 99
    _save_label(labels, public_id="pos_old_key", payload=payload)
    det = _run(_use_case(labels=labels, signing=signing), json.dumps(payload, separators=(",", ":")))
    assert det.detection_status is PositionLabelDetectionStatus.UNKNOWN_KEY_VERSION
    assert det.metadata_json.get("policy_decision") == PositionLabelPolicyDecision.REJECT.value


def test_previous_key_version_valid() -> None:
    labels = MemoryClientPositionLabelRepository()
    old_secret = "previous-secret16"
    signing = _signing(
        secret="current-secret16",
        key_version=2,
        previous=((1, old_secret),),
    )
    old_signer = _signing(secret=old_secret, key_version=1)
    payload = old_signer.sign_payload(
        build_positioning_label_payload(public_label_id="pos_rotated", version=1)
    )
    _save_label(labels, public_id="pos_rotated", payload=payload)
    det = _run(_use_case(labels=labels, signing=signing), json.dumps(payload, separators=(",", ":")))
    assert det.detection_status is PositionLabelDetectionStatus.VALID
    assert det.metadata_json.get("policy_decision") == PositionLabelPolicyDecision.ACCEPT.value


def test_client_mismatch_rejects_despite_valid_signature() -> None:
    labels = MemoryClientPositionLabelRepository()
    signing = _signing()
    payload = signing.sign_payload(
        build_positioning_label_payload(public_label_id="pos_other", version=1)
    )
    _save_label(labels, public_id="pos_other", client_id="client-owner", payload=payload)
    det = _run(
        _use_case(labels=labels, signing=signing),
        json.dumps(payload, separators=(",", ":")),
        client_id="client-scanner",
    )
    assert det.detection_status is PositionLabelDetectionStatus.CLIENT_MISMATCH
    assert det.public_identifier is None


def test_invalidated_label_rejects() -> None:
    labels = MemoryClientPositionLabelRepository()
    signing = _signing()
    payload = signing.sign_payload(
        build_positioning_label_payload(public_label_id="pos_revoked", version=1)
    )
    _save_label(
        labels,
        public_id="pos_revoked",
        payload=payload,
        status=ClientPositionLabelStatus.INVALIDATED,
    )
    det = _run(_use_case(labels=labels, signing=signing), json.dumps(payload, separators=(",", ":")))
    assert det.detection_status is PositionLabelDetectionStatus.LABEL_INVALIDATED


def test_legacy_v1_unsigned_flag_on_requires_review() -> None:
    labels = MemoryClientPositionLabelRepository()
    payload = build_positioning_label_payload(public_label_id="pos_legacy", version=1)
    _save_label(
        labels,
        public_id="pos_legacy",
        payload=payload,
        signature_status=ClientPositionLabelSignatureStatus.UNSIGNED,
    )
    raw = '{"type":"DINAMIC_POSITION","version":1,"label_id":"pos_legacy"}'
    det = _run(_use_case(labels=labels, allow_unsigned_legacy=True), raw)
    assert det.detection_status is PositionLabelDetectionStatus.LEGACY_UNSIGNED_REQUIRES_REVIEW
    assert det.metadata_json.get("policy_decision") == (
        PositionLabelPolicyDecision.ACCEPT_REQUIRES_REVIEW.value
    )
    assert det.metadata_json.get("requires_review") is True
    assert det.metadata_json.get("detail") == "missing_signature"


def test_legacy_v1_unsigned_flag_off_rejects() -> None:
    labels = MemoryClientPositionLabelRepository()
    payload = build_positioning_label_payload(public_label_id="pos_no_legacy", version=1)
    _save_label(
        labels,
        public_id="pos_no_legacy",
        payload=payload,
        signature_status=ClientPositionLabelSignatureStatus.UNSIGNED,
    )
    raw = '{"type":"DINAMIC_POSITION","version":1,"label_id":"pos_no_legacy"}'
    det = _run(_use_case(labels=labels, allow_unsigned_legacy=False), raw)
    assert det.detection_status is PositionLabelDetectionStatus.MISSING_SIGNATURE
    assert det.metadata_json.get("policy_decision") == PositionLabelPolicyDecision.REJECT.value


def test_tampered_pallet_invalidates_signature() -> None:
    labels = MemoryClientPositionLabelRepository()
    signing = _signing()
    payload = build_positioning_label_payload(
        public_label_id="pos_hier",
        pallet="01",
        side="LEFT",
        level=1,
        marker_index=1,
        marker_total=1,
    )
    signed = signing.sign_payload(payload)
    _save_label(labels, public_id="pos_hier", payload=signed)
    tampered = dict(signed)
    tampered["pallet"] = "99"
    det = _run(
        _use_case(labels=labels, signing=signing),
        json.dumps(tampered, separators=(",", ":")),
    )
    assert det.detection_status is PositionLabelDetectionStatus.INVALID_SIGNATURE
    assert det.metadata_json.get("policy_decision") == PositionLabelPolicyDecision.REJECT.value


def test_tampered_side_invalidates_signature() -> None:
    labels = MemoryClientPositionLabelRepository()
    signing = _signing()
    payload = build_positioning_label_payload(
        public_label_id="pos_side",
        pallet="01",
        side="LEFT",
        level=1,
        marker_index=1,
        marker_total=1,
    )
    signed = signing.sign_payload(payload)
    _save_label(labels, public_id="pos_side", payload=signed)
    tampered = dict(signed)
    tampered["side"] = "RIGHT"
    det = _run(
        _use_case(labels=labels, signing=signing),
        json.dumps(tampered, separators=(",", ":")),
    )
    assert det.detection_status is PositionLabelDetectionStatus.INVALID_SIGNATURE


def test_key_version_tamper_without_matching_secret_rejects() -> None:
    labels = MemoryClientPositionLabelRepository()
    signing = _signing(key_version=1)
    payload = signing.sign_payload(
        build_positioning_label_payload(public_label_id="pos_kv", version=1)
    )
    _save_label(labels, public_id="pos_kv", payload=payload)
    tampered = dict(payload)
    tampered["key_version"] = 2
    det = _run(
        _use_case(labels=labels, signing=signing),
        json.dumps(tampered, separators=(",", ":")),
    )
    assert det.detection_status in {
        PositionLabelDetectionStatus.UNKNOWN_KEY_VERSION,
        PositionLabelDetectionStatus.INVALID_SIGNATURE,
    }
    assert det.metadata_json.get("policy_decision") == PositionLabelPolicyDecision.REJECT.value


def test_catalog_hierarchy_mismatch_rejects_despite_valid_signature() -> None:
    labels = MemoryClientPositionLabelRepository()
    signing = _signing()
    qr_payload = build_positioning_label_payload(
        public_label_id="pos_mismatch",
        pallet="01",
        side="LEFT",
        level=1,
        marker_index=1,
        marker_total=1,
    )
    signed = signing.sign_payload(qr_payload)
    catalog = build_positioning_label_payload(
        public_label_id="pos_mismatch",
        pallet="04",
        side="LEFT",
        level=1,
        marker_index=1,
        marker_total=1,
    )
    _save_label(labels, public_id="pos_mismatch", payload=catalog)
    det = _run(
        _use_case(labels=labels, signing=signing),
        json.dumps(signed, separators=(",", ":")),
    )
    assert det.detection_status is PositionLabelDetectionStatus.INVALID_TYPE
    assert det.metadata_json.get("detail") == "catalog_hierarchy_mismatch"
    assert det.position_label_id is None


def test_validation_enabled_without_secret_is_not_valid() -> None:
    labels = MemoryClientPositionLabelRepository()
    empty = PositioningLabelSigningService(
        PositioningLabelSigningConfig(secret=None, key_version=1, required=False)
    )
    payload = {
        "type": "DINAMIC_POSITION",
        "version": 1,
        "label_id": "pos_nosecret",
        "key_version": 1,
        "signature": "a" * 64,
    }
    _save_label(labels, public_id="pos_nosecret", payload=payload)
    det = _run(_use_case(labels=labels, signing=empty), json.dumps(payload, separators=(",", ":")))
    assert det.detection_status is PositionLabelDetectionStatus.UNKNOWN_KEY_VERSION
    assert det.signature_status is PositionLabelSignatureStatus.UNKNOWN_KEY
    assert det.metadata_json.get("policy_decision") == PositionLabelPolicyDecision.REJECT.value


def test_label_not_found_despite_valid_signature() -> None:
    signing = _signing()
    payload = signing.sign_payload(
        build_positioning_label_payload(public_label_id="pos_ghost", version=1)
    )
    det = _run(
        _use_case(labels=MemoryClientPositionLabelRepository(), signing=signing),
        json.dumps(payload, separators=(",", ":")),
    )
    assert det.detection_status is PositionLabelDetectionStatus.LABEL_NOT_FOUND
    assert resolve_position_transition(det.detection_status) is PositionTransitionAction.CLEAR_POSITION
