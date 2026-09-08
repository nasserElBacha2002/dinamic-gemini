"""Canonical position recognition and validation services."""

from src.application.services.position_recognition.normalization import (
    CANONICAL_POSITION_CODE_MAX_LENGTH,
    NormalizedPositionCode,
    PositionCodeNormalizationError,
    normalize_position_code,
)
from src.application.services.position_recognition.shadow_comparison import (
    PositionShadowComparison,
    PositionShadowComparisonOutcome,
    compare_position_shadow,
    record_position_shadow_metric,
)
from src.application.services.position_recognition.validator import (
    CanonicalPositionValidationCommand,
    CanonicalPositionValidator,
    PositionCompatibilityPolicy,
    PositionPolicyConfigurationError,
)

__all__ = [
    "CANONICAL_POSITION_CODE_MAX_LENGTH",
    "CanonicalPositionValidationCommand",
    "CanonicalPositionValidator",
    "NormalizedPositionCode",
    "PositionCodeNormalizationError",
    "PositionCompatibilityPolicy",
    "PositionPolicyConfigurationError",
    "PositionShadowComparison",
    "PositionShadowComparisonOutcome",
    "compare_position_shadow",
    "normalize_position_code",
    "record_position_shadow_metric",
]
