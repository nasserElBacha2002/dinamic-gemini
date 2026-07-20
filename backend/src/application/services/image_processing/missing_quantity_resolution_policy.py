"""Policy for code-present / quantity-missing outcomes."""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.client_supplier.extraction_profile import (
    MissingQuantityAction,
    QuantityExtractionRules,
    QuantityPresence,
)
from src.domain.image_processing.contracts import ImageResultStatus


@dataclass(frozen=True)
class MissingQuantityDecision:
    status: ImageResultStatus
    error_code: str
    allow_external_fallback: bool
    reason: str


class MissingQuantityResolutionPolicy:
    """Map quantity rules → operational outcome when code is valid and quantity is absent."""

    def resolve(
        self,
        *,
        rules: QuantityExtractionRules,
        has_valid_internal_code: bool,
        quantity_found: bool,
    ) -> MissingQuantityDecision | None:
        if not has_valid_internal_code or quantity_found:
            return None

        presence = rules.expected_presence
        action = rules.missing_quantity_action
        required = bool(rules.required)

        if presence is QuantityPresence.OPTIONAL and not required:
            # Optional quantity: code-only is still not auto-resolved under current invariant.
            # Keep explicit UNRECOGNIZED only when configured; otherwise manual review.
            pass

        if action is MissingQuantityAction.RESOLVE_CODE_ONLY:
            # Domain invariant: never auto-resolve without quantity.
            action = MissingQuantityAction.PENDING_MANUAL_REVIEW

        if action is MissingQuantityAction.EXTERNAL_FALLBACK:
            return MissingQuantityDecision(
                status=ImageResultStatus.PENDING_MANUAL_REVIEW,
                error_code="MISSING_QUANTITY",
                allow_external_fallback=bool(rules.allow_external_fallback),
                reason="missing_quantity_action=EXTERNAL_FALLBACK",
            )
        if action is MissingQuantityAction.UNRECOGNIZED:
            return MissingQuantityDecision(
                status=ImageResultStatus.UNRECOGNIZED,
                error_code="MISSING_QUANTITY",
                allow_external_fallback=False,
                reason="missing_quantity_action=UNRECOGNIZED",
            )
        return MissingQuantityDecision(
            status=ImageResultStatus.PENDING_MANUAL_REVIEW,
            error_code="MISSING_QUANTITY",
            allow_external_fallback=bool(rules.allow_external_fallback),
            reason="missing_quantity_action=PENDING_MANUAL_REVIEW",
        )


__all__ = [
    "MissingQuantityDecision",
    "MissingQuantityResolutionPolicy",
]
