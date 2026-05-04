"""
Merge rule engine — v3.2.3.

Centralizes merge decisions: same_sku_same_group, same_sku_same_evidence,
missing_canonical_sku, ambiguous_conflict. Conservative: when in doubt, do not merge.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.domain.labels.canonicalization import canonicalize_sku
from src.domain.labels.entities import RawLabel


class MergeRule(str, Enum):
    """Explicit rule names for auditability."""

    SAME_SKU_SAME_GROUP = "same_sku_same_group"
    SAME_SKU_SAME_EVIDENCE = "same_sku_same_evidence"
    MISSING_CANONICAL_SKU = "missing_canonical_sku"
    AMBIGUOUS_CONFLICT = "ambiguous_conflict"
    NO_MERGE_SINGLE_LABEL = "no_merge_single_label"
    NO_MERGE_CONSERVATIVE = "no_merge_conservative"


@dataclass
class MergeDecision:
    """Result of evaluating a partition of raw labels."""

    should_merge: bool
    rule_name: str
    reason: str
    review_required: bool
    confidence: float | None = None


def _canonical_for_label(label: RawLabel) -> str | None:
    return canonicalize_sku(label.sku_candidate or label.sku_raw)


def _evidence_id(label: RawLabel) -> str | None:
    return label.evidence_id if label.evidence_id and str(label.evidence_id).strip() else None


def _product_names_conflict(labels: list[RawLabel]) -> bool:
    """True if we have conflicting product_name_raw that suggests different products."""
    names = set()
    for lb in labels:
        n = (lb.product_name_raw or "").strip()
        if n:
            names.add(n.upper())
    return len(names) > 1


def _confidences_inconsistent(labels: list[RawLabel]) -> bool:
    """True if confidence spread suggests ambiguity (e.g. one high, one very low)."""
    if len(labels) < 2:
        return False
    confs = [lb.confidence for lb in labels if lb.confidence is not None]
    if len(confs) < 2:
        return False
    min_c, max_c = min(confs), max(confs)
    return (max_c - min_c) > 0.5


class MergeRuleEngine:
    """
    Evaluates a partition of raw labels (same inventory, aisle, position, group_key, canonical_sku).
    Returns a single MergeDecision for the whole partition.
    """

    def evaluate(self, partition: list[RawLabel]) -> MergeDecision:
        """
        partition: raw labels already grouped by (inventory_id, aisle_id, position_id, group_key, canonical_sku).
        Caller must not pass empty partition.
        """
        if not partition:
            return MergeDecision(
                should_merge=False,
                rule_name=MergeRule.NO_MERGE_CONSERVATIVE.value,
                reason="empty_partition",
                review_required=True,
            )
        if len(partition) == 1:
            canonical = _canonical_for_label(partition[0])
            if not canonical:
                return MergeDecision(
                    should_merge=False,
                    rule_name=MergeRule.MISSING_CANONICAL_SKU.value,
                    reason="single_label_no_canonical_sku",
                    review_required=True,
                )
            return MergeDecision(
                should_merge=False,
                rule_name=MergeRule.NO_MERGE_SINGLE_LABEL.value,
                reason="single_label",
                review_required=partition[0].confidence is not None
                and partition[0].confidence < 0.5,
                confidence=partition[0].confidence,
            )

        canonical = _canonical_for_label(partition[0])
        for lb in partition[1:]:
            if _canonical_for_label(lb) != canonical:
                return MergeDecision(
                    should_merge=False,
                    rule_name=MergeRule.AMBIGUOUS_CONFLICT.value,
                    reason="canonical_sku_mismatch_in_partition",
                    review_required=True,
                )
        if not canonical:
            return MergeDecision(
                should_merge=False,
                rule_name=MergeRule.MISSING_CANONICAL_SKU.value,
                reason="no_reliable_canonical_sku",
                review_required=True,
            )
        if _product_names_conflict(partition):
            return MergeDecision(
                should_merge=False,
                rule_name=MergeRule.AMBIGUOUS_CONFLICT.value,
                reason="conflicting_product_names",
                review_required=True,
            )
        if _confidences_inconsistent(partition):
            return MergeDecision(
                should_merge=False,
                rule_name=MergeRule.AMBIGUOUS_CONFLICT.value,
                reason="inconsistent_confidence",
                review_required=True,
            )
        evidence_ids = {_evidence_id(lb) for lb in partition}
        if len(evidence_ids) == 1 and None not in evidence_ids:
            return MergeDecision(
                should_merge=True,
                rule_name=MergeRule.SAME_SKU_SAME_EVIDENCE.value,
                reason="same_sku_same_evidence",
                review_required=False,
                confidence=sum(lb.confidence or 0 for lb in partition) / len(partition),
            )
        return MergeDecision(
            should_merge=True,
            rule_name=MergeRule.SAME_SKU_SAME_GROUP.value,
            reason="same_sku_same_group",
            review_required=False,
            confidence=sum(lb.confidence or 0 for lb in partition) / len(partition),
        )
