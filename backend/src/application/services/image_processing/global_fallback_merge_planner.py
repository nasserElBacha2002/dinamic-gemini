"""Build GLOBAL_BATCH merge plan without side effects (no persistence)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from src.application.services.image_processing.global_fallback_merge_policy import (
    ExternalEntityEvidence,
    GlobalFallbackMergeAction,
    GlobalFallbackMergeDecision,
    InternalAssetEvidence,
    decide_merge_for_asset,
    decide_multi_entity_for_asset,
    decide_unmapped_entity,
    entity_fingerprint,
    normalize_provider_source_image_id,
    operation_idempotency_key,
)


@dataclass(frozen=True)
class GlobalFallbackMergeOperation:
    idempotency_key: str
    decision: GlobalFallbackMergeDecision


@dataclass
class GlobalFallbackMergePlan:
    operations: list[GlobalFallbackMergeOperation] = field(default_factory=list)
    conflicts: list[GlobalFallbackMergeDecision] = field(default_factory=list)
    unmapped: list[GlobalFallbackMergeDecision] = field(default_factory=list)
    unchanged: list[GlobalFallbackMergeDecision] = field(default_factory=list)
    skipped: list[GlobalFallbackMergeDecision] = field(default_factory=list)
    deduplicated: list[GlobalFallbackMergeDecision] = field(default_factory=list)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "apply_count": sum(
                1
                for op in self.operations
                if op.decision.action
                in (
                    GlobalFallbackMergeAction.APPLY_EXTERNAL,
                    GlobalFallbackMergeAction.COMBINE_QUANTITY,
                )
            ),
            "conflict_count": len(self.conflicts),
            "unmapped_count": len(self.unmapped),
            "keep_internal_count": len(self.unchanged),
            "skipped_count": len(self.skipped),
            "deduplicated_count": len(self.deduplicated),
            "operation_keys": [op.idempotency_key for op in self.operations],
        }


def build_merge_plan(
    *,
    batch_fingerprint: str,
    entities: Sequence[dict[str, Any]],
    evidence_by_asset: Mapping[str, InternalAssetEvidence],
    ordered_asset_ids: Sequence[str],
    frame_to_asset_map: Mapping[str, str] | None = None,
    filename_to_asset_id: Mapping[str, str] | None = None,
) -> GlobalFallbackMergePlan:
    plan = GlobalFallbackMergePlan()
    asset_ids = set(ordered_asset_ids)
    ordered = tuple(ordered_asset_ids)
    assigned: dict[str, ExternalEntityEvidence] = {}
    fmap = dict(frame_to_asset_map or {})
    # Also index ordered assets as img_N / frame_N for pipeline parity.
    for i, aid in enumerate(ordered):
        fmap.setdefault(f"img_{i}", aid)
        fmap.setdefault(f"frame_{i}", aid)
        fmap.setdefault(str(i), aid)
        fmap.setdefault(f"img_{i + 1}", aid)
        fmap.setdefault(f"frame_{i + 1}", aid)

    for ent in entities:
        if not isinstance(ent, dict):
            continue
        raw_src = ent.get("source_image_id") or ent.get("source_asset_id")
        mapped = normalize_provider_source_image_id(
            str(raw_src) if raw_src is not None else None,
            asset_id_set=asset_ids,
            filename_to_asset_id=dict(filename_to_asset_id or {}),
            frame_to_asset_map=fmap,
            ordered_asset_ids=ordered,
        )
        qty = ent.get("quantity")
        if qty is None:
            qty = ent.get("product_label_quantity")
        ext = ExternalEntityEvidence(
            internal_code=(
                str(ent.get("internal_code")).strip()
                if ent.get("internal_code") is not None
                else None
            ),
            quantity=float(qty) if isinstance(qty, (int, float)) and not isinstance(qty, bool) else None,
            confidence=float(ent["confidence"])
            if isinstance(ent.get("confidence"), (int, float))
            else None,
            source_image_id=mapped,
            raw={
                k: ent[k]
                for k in (
                    "internal_code",
                    "quantity",
                    "product_label_quantity",
                    "confidence",
                    "source_image_id",
                    "warnings",
                )
                if k in ent
            },
        )
        if mapped is None:
            plan.unmapped.append(decide_unmapped_entity(ext))
            continue
        if mapped in assigned:
            multi = decide_multi_entity_for_asset(
                asset_id=mapped, first=assigned[mapped], second=ext
            )
            if multi.reason == "duplicate_external_entity_identical":
                plan.deduplicated.append(multi)
            else:
                plan.conflicts.append(multi)
            continue
        assigned[mapped] = ext
        internal = evidence_by_asset.get(mapped) or InternalAssetEvidence(
            asset_id=mapped,
            status=None,
            internal_code=None,
            quantity=None,
            resolved_internal=False,
        )
        decision = decide_merge_for_asset(internal=internal, external=ext)
        if decision.action is GlobalFallbackMergeAction.CONFLICT_REVIEW:
            plan.conflicts.append(decision)
        elif decision.action is GlobalFallbackMergeAction.SKIP_EMPTY:
            plan.skipped.append(decision)
        elif decision.action is GlobalFallbackMergeAction.KEEP_INTERNAL:
            plan.unchanged.append(decision)
        elif decision.action in (
            GlobalFallbackMergeAction.APPLY_EXTERNAL,
            GlobalFallbackMergeAction.COMBINE_QUANTITY,
        ):
            key = operation_idempotency_key(
                batch_fingerprint=batch_fingerprint,
                asset_id=mapped,
                action=decision.action,
                entity_fingerprint=entity_fingerprint(ext),
            )
            plan.operations.append(
                GlobalFallbackMergeOperation(idempotency_key=key, decision=decision)
            )
        else:
            plan.skipped.append(decision)

    for aid in ordered:
        if aid in assigned:
            continue
        leftover: InternalAssetEvidence | None = evidence_by_asset.get(aid)
        plan.unchanged.append(decide_merge_for_asset(internal=leftover, external=None))
    return plan
