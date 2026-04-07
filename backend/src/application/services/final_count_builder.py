"""
FinalCountBuilder — v3.2.3.

Builds final count records from normalized labels only. No raw access.
Quantity = count of normalized labels per (position, sku). Propagates review_required and explanation.
"""

from __future__ import annotations

from typing import List, Optional, Tuple
from uuid import uuid4

from src.domain.labels.entities import FinalCountRecord, NormalizedLabel


def _group_key(nl: NormalizedLabel) -> Tuple[str, str, Optional[str], Optional[str]]:
    """
    Grouping key for final count.

    Important: when canonical_sku is None we do NOT group multiple normalized
    labels together, to avoid re-introducing implicit merge for ambiguous labels.
    In that case we key by the normalized label id so each becomes its own group.
    """
    if nl.canonical_sku is None:
        # Separate bucket per normalized label when SKU is unknown/ambiguous.
        return (nl.inventory_id, nl.aisle_id, nl.position_id, f"__NO_SKU__:{nl.id}")
    return (nl.inventory_id, nl.aisle_id, nl.position_id, nl.canonical_sku)


def _explanation_summary(labels: List[NormalizedLabel]) -> str:
    parts = []
    n = len(labels)
    if n == 1:
        parts.append("1 normalized label")
    else:
        parts.append(f"{n} normalized labels")
    rules = {nl.merge_rule_applied for nl in labels}
    if rules:
        parts.append("rules: " + ", ".join(sorted(rules)))
    if any(nl.review_required for nl in labels):
        parts.append("review_required")
    return "; ".join(parts)


class FinalCountBuilder:
    """Transforms normalized labels into final count records (business output)."""

    def build(
        self,
        normalized_labels: List[NormalizedLabel],
        now_factory=None,
    ) -> List[FinalCountRecord]:
        """
        Group by (inventory_id, aisle_id, position_id, canonical_sku or per-label id when sku is None).
        One FinalCountRecord per group with quantity = len(group), normalized_label_ids, explanation.
        """
        from datetime import datetime

        from datetime import timezone
        now = (now_factory or (lambda: datetime.now(timezone.utc)))()

        groups: dict = {}
        for nl in normalized_labels:
            key = _group_key(nl)
            groups.setdefault(key, []).append(nl)

        result: List[FinalCountRecord] = []
        for (inv_id, aisle_id, pos_id, sku), group in groups.items():
            quantity = len(group)
            review_required = any(nl.review_required for nl in group)
            normalized_ids = [nl.id for nl in group]
            product_name = group[0].canonical_product_name if group else None
            result.append(
                FinalCountRecord(
                    id=str(uuid4()),
                    inventory_id=inv_id,
                    aisle_id=aisle_id,
                    position_id=pos_id,
                    sku=sku,
                    product_name=product_name,
                    quantity=quantity,
                    normalized_label_ids=normalized_ids,
                    review_required=review_required,
                    explanation_summary=_explanation_summary(group),
                    metadata={},
                    created_at=now,
                    job_id=group[0].job_id,
                )
            )
        return result
