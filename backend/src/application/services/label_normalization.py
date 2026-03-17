"""
LabelNormalizationService — v3.2.3.

Transforms raw labels into normalized labels: canonicalize SKU, partition by
(inventory_id, aisle_id, position_id, group_key, canonical_sku), evaluate merge per partition.
"""

from __future__ import annotations

from datetime import timezone
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from src.domain.labels.canonicalization import canonicalize_sku
from src.domain.labels.entities import NormalizedLabel, RawLabel
from src.domain.labels.merge import MergeDecision, MergeRuleEngine


def _partition_key(label: RawLabel, canonical: Optional[str]) -> Tuple[str, str, Optional[str], str, Optional[str]]:
    return (
        label.inventory_id,
        label.aisle_id,
        label.position_id,
        label.group_key,
        canonical,
    )


class LabelNormalizationService:
    """Converts raw labels to normalized labels using canonicalization and MergeRuleEngine."""

    def __init__(self, merge_rule_engine: MergeRuleEngine) -> None:
        self._engine = merge_rule_engine

    def normalize(
        self,
        raw_labels: List[RawLabel],
        now_factory=None,
    ) -> List[NormalizedLabel]:
        """
        Partition raw labels by (inventory_id, aisle_id, position_id, group_key, canonical_sku),
        evaluate merge per partition, produce normalized labels with traceability.
        """
        from datetime import datetime

        now = (now_factory or (lambda: datetime.now(timezone.utc)))()

        partitions: Dict[Tuple[str, str, Optional[str], str, Optional[str]], List[RawLabel]] = {}
        for label in raw_labels:
            canonical = canonicalize_sku(label.sku_candidate or label.sku_raw)
            key = _partition_key(label, canonical)
            partitions.setdefault(key, []).append(label)

        result: List[NormalizedLabel] = []
        for part_labels in partitions.values():
            decision = self._engine.evaluate(part_labels)
            if decision.should_merge:
                nl = self._build_merged(part_labels, decision, now)
                result.append(nl)
            else:
                for rl in part_labels:
                    nl = self._build_single(rl, decision, now)
                    result.append(nl)
        return result

    def _build_merged(
        self,
        labels: List[RawLabel],
        decision: MergeDecision,
        now,
    ) -> NormalizedLabel:
        first = labels[0]
        canonical = canonicalize_sku(first.sku_candidate or first.sku_raw)
        product_name = first.product_name_raw
        # Use first label's position_id as primary for merged result
        position_id = first.position_id
        raw_ids = [lb.id for lb in labels]
        return NormalizedLabel(
            id=str(uuid4()),
            inventory_id=first.inventory_id,
            aisle_id=first.aisle_id,
            position_id=position_id,
            group_key=first.group_key,
            canonical_sku=canonical,
            canonical_product_name=product_name,
            raw_label_ids=raw_ids,
            merge_rule_applied=decision.rule_name,
            merge_confidence=decision.confidence,
            merge_reason=decision.reason,
            review_required=decision.review_required,
            metadata={"raw_count": len(labels)},
            created_at=now,
        )

    def _build_single(
        self,
        label: RawLabel,
        decision: MergeDecision,
        now,
    ) -> NormalizedLabel:
        canonical = canonicalize_sku(label.sku_candidate or label.sku_raw)
        return NormalizedLabel(
            id=str(uuid4()),
            inventory_id=label.inventory_id,
            aisle_id=label.aisle_id,
            position_id=label.position_id,
            group_key=label.group_key,
            canonical_sku=canonical,
            canonical_product_name=label.product_name_raw,
            raw_label_ids=[label.id],
            merge_rule_applied=decision.rule_name,
            merge_confidence=decision.confidence,
            merge_reason=decision.reason,
            review_required=decision.review_required,
            metadata={},
            created_at=now,
        )
