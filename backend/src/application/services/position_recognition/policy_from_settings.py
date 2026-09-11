"""Build PositionCompatibilityPolicy from LimitsAndSchemaSettings."""

from __future__ import annotations

from typing import Protocol

from src.application.services.position_recognition.channel_gates import (
    FlexiblePositionChannel,
    FlexiblePositionChannelSettings,
    is_flexible_channel_enabled,
)
from src.application.services.position_recognition.validator import PositionCompatibilityPolicy
from src.domain.position_recognition import PositionSignaturePolicy


class PositionPolicySettings(Protocol):
    position_label_signature_validation_enabled: bool
    positioning_allow_unsigned_legacy: bool
    position_preexistence_required: bool
    position_flexible_validation_enabled: bool
    position_signature_policy: str


def _parse_signature_policy(raw: object) -> PositionSignaturePolicy:
    text = str(raw or "REQUIRED").strip().upper()
    try:
        return PositionSignaturePolicy(text)
    except ValueError as exc:
        raise ValueError(
            "POSITION_SIGNATURE_POLICY must be REQUIRED, OPTIONAL, or NOT_APPLICABLE"
        ) from exc


def resolve_position_compatibility_policy(
    settings: PositionPolicySettings,
) -> PositionCompatibilityPolicy:
    signature_policy = _parse_signature_policy(settings.position_signature_policy)
    return PositionCompatibilityPolicy.resolve(
        signature_validation_enabled=bool(settings.position_label_signature_validation_enabled),
        allow_unsigned_legacy=bool(settings.positioning_allow_unsigned_legacy),
        preexistence_required=bool(settings.position_preexistence_required),
        flexible_validation_enabled=bool(settings.position_flexible_validation_enabled),
        signature_policy=signature_policy,
    )


def resolve_effective_position_policy(
    channel: FlexiblePositionChannel,
    settings: PositionPolicySettings,
    profile_signature_policy: PositionSignaturePolicy | str | None,
    capability_enforced: bool,
    *,
    channel_settings: FlexiblePositionChannelSettings | None = None,
) -> PositionCompatibilityPolicy:
    """Resolve productive policy for a channel given settings + profile + capability mode.

    - Channel off or capability not ENFORCED → legacy (settings preexistence + signature
      from profile when provided, else settings kill-switch default).
    - Channel on + ENFORCED → flexible (preexistence=false, flexible=true, signature from profile).
    """
    if channel_settings is not None:
        channel_on = is_flexible_channel_enabled(channel_settings, channel)
    else:
        channel_on = is_flexible_channel_enabled(settings, channel)  # type: ignore[arg-type]
    if profile_signature_policy is not None:
        signature_policy = (
            profile_signature_policy
            if isinstance(profile_signature_policy, PositionSignaturePolicy)
            else _parse_signature_policy(profile_signature_policy)
        )
    else:
        signature_policy = _parse_signature_policy(settings.position_signature_policy)

    if channel_on and capability_enforced:
        return PositionCompatibilityPolicy.resolve(
            signature_validation_enabled=bool(
                settings.position_label_signature_validation_enabled
            ),
            allow_unsigned_legacy=bool(settings.positioning_allow_unsigned_legacy),
            preexistence_required=False,
            flexible_validation_enabled=True,
            signature_policy=signature_policy,
        )

    # Channel off or capability not ENFORCED → classic legacy snapshot.
    return PositionCompatibilityPolicy.resolve(
        signature_validation_enabled=bool(settings.position_label_signature_validation_enabled),
        allow_unsigned_legacy=bool(settings.positioning_allow_unsigned_legacy),
        preexistence_required=True,
        flexible_validation_enabled=False,
        signature_policy=signature_policy,
    )
