"""Validate DINAMIC_POSITION signatures (Phase 3)."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.services.position_label_detection.payload_parser import (
    ParsedPositionLabelPayload,
)
from src.application.services.positioning_label_signing import PositioningLabelSigningService
from src.domain.position_label_detection.entities import (
    PositionLabelDetectionStatus,
    PositionLabelSignatureStatus,
)


@dataclass(frozen=True)
class PositionLabelValidationResult:
    detection_status: PositionLabelDetectionStatus
    signature_status: PositionLabelSignatureStatus
    detail: str | None = None


class PositionLabelValidationService:
    def __init__(
        self,
        *,
        signing: PositioningLabelSigningService,
        signature_validation_enabled: bool,
    ) -> None:
        self._signing = signing
        self._signature_validation_enabled = bool(signature_validation_enabled)

    def validate(self, parsed: ParsedPositionLabelPayload) -> PositionLabelValidationResult:
        if parsed.status is not PositionLabelDetectionStatus.VALID:
            sig = PositionLabelSignatureStatus.MISSING
            if parsed.status is PositionLabelDetectionStatus.INVALID_SIGNATURE:
                sig = PositionLabelSignatureStatus.INVALID
            elif parsed.status is PositionLabelDetectionStatus.UNKNOWN_KEY_VERSION:
                sig = PositionLabelSignatureStatus.UNKNOWN_KEY
            elif parsed.status is PositionLabelDetectionStatus.MISSING_SIGNATURE:
                sig = PositionLabelSignatureStatus.MISSING
            return PositionLabelValidationResult(
                detection_status=parsed.status,
                signature_status=sig,
                detail=parsed.detail,
            )
        if not self._signature_validation_enabled:
            return PositionLabelValidationResult(
                detection_status=PositionLabelDetectionStatus.SIGNATURE_VALIDATION_SKIPPED,
                signature_status=PositionLabelSignatureStatus.SKIPPED,
                detail="signature validation disabled — not operationally VALID",
            )
        assert parsed.payload is not None
        key_version = int(parsed.key_version or 0)
        if key_version < 1 or not self._signing.has_secret_for_version(key_version):
            return PositionLabelValidationResult(
                detection_status=PositionLabelDetectionStatus.UNKNOWN_KEY_VERSION,
                signature_status=PositionLabelSignatureStatus.UNKNOWN_KEY,
                detail="unknown key_version",
            )
        try:
            ok = self._signing.verify_payload(parsed.payload)
        except ValueError as exc:
            return PositionLabelValidationResult(
                detection_status=PositionLabelDetectionStatus.INVALID_SIGNATURE,
                signature_status=PositionLabelSignatureStatus.INVALID,
                detail=str(exc),
            )
        if not ok:
            return PositionLabelValidationResult(
                detection_status=PositionLabelDetectionStatus.INVALID_SIGNATURE,
                signature_status=PositionLabelSignatureStatus.INVALID,
                detail="HMAC mismatch",
            )
        return PositionLabelValidationResult(
            detection_status=PositionLabelDetectionStatus.VALID,
            signature_status=PositionLabelSignatureStatus.VALID,
        )
