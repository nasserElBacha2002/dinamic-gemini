"""Golden roundtrip: generator v2 payload → detection parser → HMAC VALID."""

from __future__ import annotations

import json

from src.application.services.position_label_detection.payload_parser import (
    PositionLabelPayloadParser,
)
from src.application.services.position_label_detection.validation_service import (
    PositionLabelValidationService,
)
from src.application.services.positioning_label_signing import (
    PositioningLabelSigningConfig,
    PositioningLabelSigningService,
)
from src.domain.aisle_location.label_entities import POSITIONING_LABEL_PAYLOAD_VERSION_V2
from src.domain.aisle_location.payload import (
    build_positioning_label_payload,
    canonicalize_positioning_payload,
)
from src.domain.position_label_detection.entities import (
    PositionLabelDetectionStatus,
    PositionLabelSignatureStatus,
)


def _signing() -> PositioningLabelSigningService:
    return PositioningLabelSigningService(
        PositioningLabelSigningConfig(secret="test-position-hmac-secret", key_version=1)
    )


def test_position_v2_generator_parser_hmac_roundtrip() -> None:
    signing = _signing()
    unsigned = build_positioning_label_payload(
        public_label_id="pos_golden_v2_01",
        pallet="04",
        side="LEFT",
        level=2,
        marker_index=1,
        marker_total=3,
    )
    assert unsigned["version"] == POSITIONING_LABEL_PAYLOAD_VERSION_V2
    signed = signing.sign_payload(unsigned)
    assert "signature" in signed and "key_version" in signed
    raw_qr = canonicalize_positioning_payload(signed)

    parsed = PositionLabelPayloadParser(max_payload_bytes=4096).parse(raw_qr)
    assert parsed.status is PositionLabelDetectionStatus.VALID
    assert parsed.version == 2
    assert parsed.label_id == "pos_golden_v2_01"
    assert parsed.signature
    assert parsed.payload is not None
    assert parsed.payload["pallet"] == "04"
    assert parsed.payload["side"] == "LEFT"
    assert parsed.payload["level"] == 2
    assert parsed.payload["marker_index"] == 1
    assert parsed.payload["marker_total"] == 3

    validated = PositionLabelValidationService(
        signing=signing, signature_validation_enabled=True
    ).validate(parsed)
    assert validated.detection_status is PositionLabelDetectionStatus.VALID
    assert validated.signature_status is PositionLabelSignatureStatus.VALID


def test_position_v2_unsupported_is_not_unsupported_version() -> None:
    """Regression: printed hierarchy labels must not classify as UNSUPPORTED_VERSION."""
    signing = _signing()
    signed = signing.sign_payload(
        build_positioning_label_payload(
            public_label_id="pos_v2_ok",
            pallet="P1",
            side="RIGHT",
            level=1,
            marker_index=2,
            marker_total=2,
        )
    )
    raw = json.dumps(signed, sort_keys=True, separators=(",", ":"))
    parsed = PositionLabelPayloadParser(max_payload_bytes=4096).parse(raw)
    assert parsed.status is not PositionLabelDetectionStatus.UNSUPPORTED_VERSION
    assert parsed.status is PositionLabelDetectionStatus.VALID


def test_unknown_version_still_unsupported_and_signature_not_falsely_missing() -> None:
    raw = (
        '{"type":"DINAMIC_POSITION","version":99,"label_id":"pos_x",'
        '"signature":"abcd","key_version":1}'
    )
    parsed = PositionLabelPayloadParser(max_payload_bytes=4096).parse(raw)
    assert parsed.status is PositionLabelDetectionStatus.UNSUPPORTED_VERSION
    assert parsed.signature == "abcd"
    validated = PositionLabelValidationService(
        signing=_signing(), signature_validation_enabled=True
    ).validate(parsed)
    assert validated.signature_status is PositionLabelSignatureStatus.INVALID


def test_position_v2_missing_signature_is_missing_not_legacy() -> None:
    raw = (
        '{"type":"DINAMIC_POSITION","version":2,"label_id":"pos_v2_nosig",'
        '"pallet":"02","side":"LEFT","level":1,"marker_index":1,"marker_total":1}'
    )
    parsed = PositionLabelPayloadParser(max_payload_bytes=4096).parse(raw)
    assert parsed.status is PositionLabelDetectionStatus.MISSING_SIGNATURE
    assert parsed.version == 2
    assert not parsed.signature
