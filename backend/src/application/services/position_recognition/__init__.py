"""Canonical position recognition and validation services."""

from src.application.services.position_recognition.accept_coordinator import (
    AcceptPositionCoordinator,
    AcceptPositionOutcome,
    AcceptPositionRequest,
)
from src.application.services.position_recognition.channel_gates import (
    FlexiblePositionChannel,
    is_flexible_channel_enabled,
)
from src.application.services.position_recognition.flexible_shadow import (
    FlexibleShadowComparison,
    FlexibleShadowDivergenceCategory,
    FlexibleShadowEvaluation,
    FlexibleShadowOutcome,
    PositionFlexibleShadowEvaluator,
    compare_flexible_shadow,
    flexible_shadow_policy,
)
from src.application.services.position_recognition.normalization import (
    CANONICAL_POSITION_CODE_MAX_LENGTH,
    NormalizedPositionCode,
    PositionCodeNormalizationError,
    normalize_position_code,
)
from src.application.services.position_recognition.policy_from_settings import (
    resolve_effective_position_policy,
    resolve_position_compatibility_policy,
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
from src.domain.position_recognition import PositionSignaturePolicy

__all__ = [
    "AcceptPositionCoordinator",
    "AcceptPositionOutcome",
    "AcceptPositionRequest",
    "CANONICAL_POSITION_CODE_MAX_LENGTH",
    "CanonicalPositionValidationCommand",
    "CanonicalPositionValidator",
    "FlexiblePositionChannel",
    "FlexibleShadowComparison",
    "FlexibleShadowDivergenceCategory",
    "FlexibleShadowEvaluation",
    "FlexibleShadowOutcome",
    "NormalizedPositionCode",
    "PositionCodeNormalizationError",
    "PositionCompatibilityPolicy",
    "PositionFlexibleShadowEvaluator",
    "PositionPolicyConfigurationError",
    "PositionShadowComparison",
    "PositionShadowComparisonOutcome",
    "PositionSignaturePolicy",
    "compare_flexible_shadow",
    "compare_position_shadow",
    "flexible_shadow_policy",
    "is_flexible_channel_enabled",
    "normalize_position_code",
    "record_position_shadow_metric",
    "resolve_effective_position_policy",
    "resolve_position_compatibility_policy",
]
