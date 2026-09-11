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


def is_unsigned_legacy_catalog_match(
    *,
    parsed_label_id: str,
    parsed_version: int,
    label: ClientPositionLabel,
) -> bool:
    """Legacy REQUIRED path: only catalog-registered v1 UNSIGNED labels."""
    return is_unsigned_catalog_match(
        parsed_label_id=parsed_label_id,
        parsed_version=parsed_version,
        label=label,
        allowed_versions=frozenset({1}),
    )


def is_unsigned_catalog_match(
    *,
    parsed_label_id: str,
    parsed_version: int,
    label: ClientPositionLabel,
    allowed_versions: frozenset[int] | None = None,
) -> bool:
    """Catalog UNSIGNED Dinamic match — shared by legacy and flexible accept paths."""
    versions = allowed_versions if allowed_versions is not None else frozenset({1})
    if int(parsed_version or 0) not in versions:
        return False
    if label.signature_status is not ClientPositionLabelSignatureStatus.UNSIGNED:
        return False
    stored = label.canonical_payload or {}
    stored_version = int(stored.get("version") or 0)
    return (
        not stored.get("signature")
        and (stored.get("type") or "").strip() == "DINAMIC_POSITION"
        and (stored.get("label_id") or "").strip() == parsed_label_id.strip()
        and stored_version == int(parsed_version or 0)
        and stored_version in versions
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

    # Dinamic positioning payload versions that may be accepted unsigned under flexible/OPTIONAL.
    _FLEXIBLE_UNSIGNED_VERSIONS = frozenset({1, 2})

    def __init__(
        self,
        *,
        resolver: PositionLabelResolver,
        allow_unsigned_legacy: bool = True,
        allow_flexible_unsigned: bool = False,
    ) -> None:
        self._resolver = resolver
        self._allow_unsigned_legacy = bool(allow_unsigned_legacy)
        self._allow_flexible_unsigned = bool(allow_flexible_unsigned)

    @property
    def allow_unsigned_legacy(self) -> bool:
        return self._allow_unsigned_legacy

    @property
    def allow_flexible_unsigned(self) -> bool:
        return self._allow_flexible_unsigned

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
        # v2+ on the REQUIRED/legacy path must carry signature — use flexible accept instead.
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
        if not is_unsigned_legacy_catalog_match(
            parsed_label_id=parsed.label_id,
            parsed_version=int(parsed.version or 0),
            label=label,
        ):
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

    def try_accept_unsigned_flexible(
        self,
        *,
        parsed: ParsedPositionLabelPayload,
        expected_client_id: str,
    ) -> PositionLabelPolicyOutcome | None:
        """OPTIONAL/flexible: accept catalog UNSIGNED Dinamic labels (v1/v2) without QR signature.

        Still requires a tenant-scoped catalog match and hierarchy-compatible payload.
        Invalid signatures are never accepted here (parser status must be MISSING_SIGNATURE).
        """
        if not self._allow_flexible_unsigned:
            return None
        if parsed.status is not PositionLabelDetectionStatus.MISSING_SIGNATURE:
            return None
        if not parsed.label_id:
            return None
        version = int(parsed.version or 0)
        if version not in self._FLEXIBLE_UNSIGNED_VERSIONS:
            return None

        resolved = self._resolver.resolve(
            public_label_id=parsed.label_id,
            expected_client_id=expected_client_id,
        )
        if resolved.detection_status is not PositionLabelDetectionStatus.VALID:
            return None
        assert resolved.label is not None
        label = resolved.label
        if not is_unsigned_catalog_match(
            parsed_label_id=parsed.label_id,
            parsed_version=version,
            label=label,
            allowed_versions=self._FLEXIBLE_UNSIGNED_VERSIONS,
        ):
            return None

        return PositionLabelPolicyOutcome(
            detection_status=PositionLabelDetectionStatus.VALID,
            signature_status=PositionLabelSignatureStatus.MISSING,
            policy_decision=PositionLabelPolicyDecision.ACCEPT,
            requires_review=False,
            label=label,
            detail="flexible_unsigned_accepted",
            metadata={
                "policy_decision": PositionLabelPolicyDecision.ACCEPT.value,
                "requires_review": False,
                "signature_validation_status": PositionLabelSignatureStatus.MISSING.value,
                "flexible_unsigned_accept": True,
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
