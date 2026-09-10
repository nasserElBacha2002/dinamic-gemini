"""Build PositionCompatibilityPolicy from LimitsAndSchemaSettings."""

from __future__ import annotations

from typing import Protocol

from src.application.services.position_recognition.validator import PositionCompatibilityPolicy
from src.domain.position_recognition import PositionSignaturePolicy


class PositionPolicySettings(Protocol):
    position_label_signature_validation_enabled: bool
    positioning_allow_unsigned_legacy: bool
    position_preexistence_required: bool
    position_flexible_validation_enabled: bool
    position_signature_policy: str


def resolve_position_compatibility_policy(
    settings: PositionPolicySettings,
) -> PositionCompatibilityPolicy:
    raw = str(settings.position_signature_policy or "REQUIRED").strip().upper()
    try:
        signature_policy = PositionSignaturePolicy(raw)
    except ValueError as exc:
        raise ValueError(
            "POSITION_SIGNATURE_POLICY must be REQUIRED, OPTIONAL, or NOT_APPLICABLE"
        ) from exc
    return PositionCompatibilityPolicy.resolve(
        signature_validation_enabled=bool(settings.position_label_signature_validation_enabled),
        allow_unsigned_legacy=bool(settings.positioning_allow_unsigned_legacy),
        preexistence_required=bool(settings.position_preexistence_required),
        flexible_validation_enabled=bool(settings.position_flexible_validation_enabled),
        signature_policy=signature_policy,
    )
