"""Canonical position recognition and validation services."""

from src.application.services.position_recognition.normalization import (
    CANONICAL_POSITION_CODE_MAX_LENGTH,
    NormalizedPositionCode,
    PositionCodeNormalizationError,
    normalize_position_code,
)
from src.application.services.position_recognition.validator import (
    CanonicalPositionValidationCommand,
    CanonicalPositionValidator,
    PositionCompatibilityPolicy,
)

__all__ = [
    "CANONICAL_POSITION_CODE_MAX_LENGTH",
    "CanonicalPositionValidationCommand",
    "CanonicalPositionValidator",
    "NormalizedPositionCode",
    "PositionCodeNormalizationError",
    "PositionCompatibilityPolicy",
    "normalize_position_code",
]
