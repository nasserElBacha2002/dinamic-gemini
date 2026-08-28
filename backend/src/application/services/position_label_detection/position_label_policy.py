"""Position-label policy: separate cryptographic validation from acceptance decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.application.services.position_label_detection.payload_parser import (
    ParsedPositionLabelPayload,
)
from src.application.services.position_label_detection.resolver import PositionLabelResolver
from src.domain.client_position_label.entities import (
    ClientPositionLabel,
    ClientPositionLabelSignatureStatus,
)
from src.domain.position_label_detection.entities import (
    PositionLabelDetectionStatus,
    PositionLabelSignatureStatus,
)


class PositionLabelPolicyDecision(str, Enum):
    ACCEPT = "ACCEPT"
    ACCEPT_REQUIRES_REVIEW = "ACCEPT_REQUIRES_REVIEW"
    REJECT = "REJECT"


@dataclass(frozen=True)
class PositionLabelPolicyOutcome:
    detection_status: PositionLabelDetectionStatus
    signature_status: PositionLabelSignatureStatus
    policy_decision: PositionLabelPolicyDecision
    requires_review: bool
    label: ClientPositionLabel | None = None
    detail: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class PositionLabelPolicyService:
    """Centralizes unsigned-legacy compatibility and observability policy fields."""

    def __init__(
        self,
        *,
        resolver: PositionLabelResolver,
        allow_unsigned_legacy: bool = True,
    ) -> None:
        self._resolver = resolver
        self._allow_unsigned_legacy = bool(allow_unsigned_legacy)

    @property
    def allow_unsigned_legacy(self) -> bool:
        return self._allow_unsigned_legacy

    def try_accept_unsigned_legacy(
        self,
        *,
        parsed: ParsedPositionLabelPayload,
        expected_client_id: str,
    ) -> PositionLabelPolicyOutcome | None:
        """Catalog-registered v1 UNSIGNED labels without QR signature (compat path)."""
        if not self._allow_unsigned_legacy:
            return None
        if parsed.status is not PositionLabelDetectionStatus.MISSING_SIGNATURE:
            return None
        if not parsed.label_id:
            return None
        # v2+ payloads must carry signature on the QR — never downgrade to legacy unsigned.
        if int(parsed.version or 0) != 1:
            return None

        resolved = self._resolver.resolve(
            public_label_id=parsed.label_id,
            expected_client_id=expected_client_id,
        )
        if resolved.detection_status is not PositionLabelDetectionStatus.VALID:
            return None
        assert resolved.label is not None
        label = resolved.label
        if label.signature_status is not ClientPositionLabelSignatureStatus.UNSIGNED:
            return None

        stored = label.canonical_payload or {}
        if stored.get("signature"):
            return None
        if (stored.get("type") or "").strip() != "DINAMIC_POSITION":
            return None
        if (stored.get("label_id") or "").strip() != parsed.label_id.strip():
            return None
        if int(stored.get("version") or 0) != 1:
            return None

        return PositionLabelPolicyOutcome(
            detection_status=PositionLabelDetectionStatus.LEGACY_UNSIGNED_REQUIRES_REVIEW,
            signature_status=PositionLabelSignatureStatus.MISSING,
            policy_decision=PositionLabelPolicyDecision.ACCEPT_REQUIRES_REVIEW,
            requires_review=True,
            label=label,
            detail="missing_signature",
            metadata={
                "policy_decision": PositionLabelPolicyDecision.ACCEPT_REQUIRES_REVIEW.value,
                "requires_review": True,
                "signature_validation_status": PositionLabelSignatureStatus.MISSING.value,
                "unsigned_legacy_compat": True,
            },
        )

    @staticmethod
    def metadata_for_accept(
        *,
        signature_status: PositionLabelSignatureStatus,
        requires_review: bool = False,
    ) -> dict[str, Any]:
        decision = (
            PositionLabelPolicyDecision.ACCEPT_REQUIRES_REVIEW
            if requires_review
            else PositionLabelPolicyDecision.ACCEPT
        )
        return {
            "policy_decision": decision.value,
            "requires_review": requires_review,
            "signature_validation_status": signature_status.value,
        }

    @staticmethod
    def metadata_for_reject(
        *,
        signature_status: PositionLabelSignatureStatus,
        validation_status: PositionLabelDetectionStatus,
    ) -> dict[str, Any]:
        return {
            "policy_decision": PositionLabelPolicyDecision.REJECT.value,
            "requires_review": False,
            "signature_validation_status": signature_status.value,
            "validation_status": validation_status.value,
        }
