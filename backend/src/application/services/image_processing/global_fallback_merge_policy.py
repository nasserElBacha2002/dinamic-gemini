"""Explicit OCR ∩ GLOBAL_BATCH LLM merge policy (tested matrix)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class GlobalFallbackMergeAction(str, Enum):
    KEEP_INTERNAL = "KEEP_INTERNAL"
    APPLY_EXTERNAL = "APPLY_EXTERNAL"
    COMBINE_QUANTITY = "COMBINE_QUANTITY"
    CONFLICT_REVIEW = "CONFLICT_REVIEW"
    UNMAPPED_REVIEW = "UNMAPPED_REVIEW"
    SKIP_EMPTY = "SKIP_EMPTY"


@dataclass(frozen=True)
class InternalAssetEvidence:
    asset_id: str
    status: str | None
    internal_code: str | None
    quantity: float | None
    resolved_internal: bool = False


@dataclass(frozen=True)
class ExternalEntityEvidence:
    internal_code: str | None
    quantity: float | None
    confidence: float | None = None
    source_image_id: str | None = None
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class GlobalFallbackMergeDecision:
    action: GlobalFallbackMergeAction
    asset_id: str | None
    reason: str
    external: ExternalEntityEvidence | None = None
    internal: InternalAssetEvidence | None = None


def _norm_code(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _has_valid_quantity(quantity: float | None) -> bool:
    if quantity is None:
        return False
    try:
        return float(quantity) > 0
    except (TypeError, ValueError):
        return False


def decide_merge_for_asset(
    *,
    internal: InternalAssetEvidence | None,
    external: ExternalEntityEvidence | None,
) -> GlobalFallbackMergeDecision:
    """Decide how to reconcile one asset's internal OCR with one external entity."""
    asset_id = (internal.asset_id if internal else None) or (
        external.source_image_id if external else None
    )

    if external is None:
        return GlobalFallbackMergeDecision(
            action=GlobalFallbackMergeAction.KEEP_INTERNAL,
            asset_id=asset_id,
            reason="fallback_empty_keep_internal",
            internal=internal,
        )

    ext_code = _norm_code(external.internal_code)
    ext_qty_ok = _has_valid_quantity(external.quantity)
    if not ext_code or not ext_qty_ok:
        return GlobalFallbackMergeDecision(
            action=GlobalFallbackMergeAction.SKIP_EMPTY,
            asset_id=asset_id,
            reason="external_entity_incomplete",
            external=external,
            internal=internal,
        )

    if internal is None:
        return GlobalFallbackMergeDecision(
            action=GlobalFallbackMergeAction.APPLY_EXTERNAL,
            asset_id=asset_id,
            reason="no_internal_apply_external",
            external=external,
        )

    int_code = _norm_code(internal.internal_code)
    int_qty_ok = _has_valid_quantity(internal.quantity)

    if internal.resolved_internal and int_code and int_qty_ok:
        if int_code == ext_code:
            return GlobalFallbackMergeDecision(
                action=GlobalFallbackMergeAction.KEEP_INTERNAL,
                asset_id=asset_id,
                reason="internal_valid_matches_external",
                external=external,
                internal=internal,
            )
        return GlobalFallbackMergeDecision(
            action=GlobalFallbackMergeAction.CONFLICT_REVIEW,
            asset_id=asset_id,
            reason="internal_external_code_conflict",
            external=external,
            internal=internal,
        )

    if int_code and not int_qty_ok and int_code == ext_code and ext_qty_ok:
        return GlobalFallbackMergeDecision(
            action=GlobalFallbackMergeAction.COMBINE_QUANTITY,
            asset_id=asset_id,
            reason="complete_quantity_from_external",
            external=external,
            internal=internal,
        )

    if not int_code:
        return GlobalFallbackMergeDecision(
            action=GlobalFallbackMergeAction.APPLY_EXTERNAL,
            asset_id=asset_id,
            reason="internal_unresolved_apply_external",
            external=external,
            internal=internal,
        )

    if int_code != ext_code:
        return GlobalFallbackMergeDecision(
            action=GlobalFallbackMergeAction.CONFLICT_REVIEW,
            asset_id=asset_id,
            reason="code_mismatch_review",
            external=external,
            internal=internal,
        )

    return GlobalFallbackMergeDecision(
        action=GlobalFallbackMergeAction.APPLY_EXTERNAL,
        asset_id=asset_id,
        reason="apply_external_default",
        external=external,
        internal=internal,
    )


def decide_unmapped_entity(external: ExternalEntityEvidence) -> GlobalFallbackMergeDecision:
    """Entity without a safe asset association → review, never invent links."""
    return GlobalFallbackMergeDecision(
        action=GlobalFallbackMergeAction.UNMAPPED_REVIEW,
        asset_id=None,
        reason="entity_without_trusted_asset",
        external=external,
    )


def normalize_provider_source_image_id(
    raw_id: str | None,
    *,
    asset_id_set: set[str],
    filename_to_asset_id: dict[str, str] | None = None,
) -> str | None:
    """Map provider source_image_id toward an internal asset id when safe."""
    if not raw_id:
        return None
    text = str(raw_id).strip()
    if not text:
        return None
    if text in asset_id_set:
        return text
    # Common hybrid forms: "img_3", sequence numbers, filenames.
    mapping = filename_to_asset_id or {}
    if text in mapping:
        return mapping[text]
    lower = text.lower()
    for name, aid in mapping.items():
        if name.lower() == lower:
            return aid
    return None
