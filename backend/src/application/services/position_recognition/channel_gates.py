"""Channel rollout gates for flexible position validation."""

from __future__ import annotations

from enum import Enum
from typing import Protocol


class FlexiblePositionChannel(str, Enum):
    CODE_SCAN = "CODE_SCAN"
    VISION = "VISION"
    MOBILE = "MOBILE"
    IMPORT = "IMPORT"
    REVIEW = "REVIEW"


class FlexiblePositionChannelSettings(Protocol):
    position_flexible_validation_enabled: bool
    position_flexible_code_scan_enabled: bool
    position_flexible_vision_enabled: bool
    position_flexible_mobile_enabled: bool
    position_flexible_import_enabled: bool
    position_flexible_review_enabled: bool
    position_import_materialization_enabled: bool


def is_flexible_channel_enabled(
    settings: FlexiblePositionChannelSettings,
    channel: FlexiblePositionChannel,
) -> bool:
    """Return True when the master flexible gate and the channel flag are both on.

    Import also requires ``POSITION_IMPORT_MATERIALIZATION_ENABLED`` (which itself
    requires auto-materialization at settings composition time).
    """
    if not settings.position_flexible_validation_enabled:
        return False
    if channel is FlexiblePositionChannel.CODE_SCAN:
        return bool(settings.position_flexible_code_scan_enabled)
    if channel is FlexiblePositionChannel.VISION:
        return bool(settings.position_flexible_vision_enabled)
    if channel is FlexiblePositionChannel.MOBILE:
        return bool(settings.position_flexible_mobile_enabled)
    if channel is FlexiblePositionChannel.IMPORT:
        return bool(settings.position_flexible_import_enabled) and bool(
            settings.position_import_materialization_enabled
        )
    if channel is FlexiblePositionChannel.REVIEW:
        return bool(settings.position_flexible_review_enabled)
    return False
