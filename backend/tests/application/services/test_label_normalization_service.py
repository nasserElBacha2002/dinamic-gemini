"""Unit tests for LabelNormalizationService — v3.2.3."""

from datetime import datetime, timezone

from src.application.services.label_normalization import LabelNormalizationService
from src.domain.labels.entities import RawLabel
from src.domain.labels.merge import MergeRuleEngine


def _raw(
    id_: str,
    position_id: str = "pos1",
    group_key: str = "g1",
    evidence_id: str = "ev1",
    sku_raw: str = "SKU-A",
    sku_candidate: str | None = None,
) -> RawLabel:
    cand = sku_candidate if sku_candidate is not None else sku_raw
    return RawLabel(
        id=id_,
        inventory_id="inv1",
        aisle_id="aisle1",
        position_id=position_id,
        evidence_id=evidence_id,
        group_key=group_key,
        provider="pipeline",
        source_type="hybrid",
        source_reference=None,
        sku_raw=sku_raw,
        sku_candidate=cand,
        product_name_raw=None,
        detected_text=None,
        confidence=0.9,
        metadata={},
        created_at=datetime.now(timezone.utc),
    )


def test_three_raw_one_normalized():
    """3 raw labels same SKU same group → 1 normalized (merge)."""
    engine = MergeRuleEngine()
    service = LabelNormalizationService(merge_rule_engine=engine)
    raw_labels = [
        _raw("r1", group_key="g1", sku_raw="SKU-X"),
        _raw("r2", group_key="g1", sku_raw="SKU-X"),
        _raw("r3", group_key="g1", sku_raw="SKU-X"),
    ]
    normalized = service.normalize(raw_labels)
    assert len(normalized) == 1
    assert normalized[0].canonical_sku == "SKU-X"
    assert set(normalized[0].raw_label_ids) == {"r1", "r2", "r3"}
    assert normalized[0].merge_rule_applied in ("same_sku_same_group", "same_sku_same_evidence")


def test_two_raw_two_normalized_different_groups():
    """2 raw same SKU but different group_key → 2 partitions → 2 normalized."""
    engine = MergeRuleEngine()
    service = LabelNormalizationService(merge_rule_engine=engine)
    raw_labels = [
        _raw("r1", group_key="g1", sku_raw="SKU-Y"),
        _raw("r2", group_key="g2", sku_raw="SKU-Y"),
    ]
    normalized = service.normalize(raw_labels)
    assert len(normalized) == 2
    ids = {nl.raw_label_ids[0] for nl in normalized}
    assert ids == {"r1", "r2"}


def test_null_sku_no_merge():
    """Raw with no reliable SKU → each stays separate (missing_canonical_sku)."""
    engine = MergeRuleEngine()
    service = LabelNormalizationService(merge_rule_engine=engine)
    raw_labels = [
        _raw("r1", sku_raw="", sku_candidate=""),
        _raw("r2", sku_raw="", sku_candidate=""),
    ]
    # Empty string canonicalizes to None; they'll be in same partition (same key with canonical None)
    normalized = service.normalize(raw_labels)
    # Engine says no merge; so 2 normalized
    assert len(normalized) == 2
    assert all(nl.merge_rule_applied == "missing_canonical_sku" for nl in normalized)


def test_mixed_partitions():
    """Two groups: one merges 2, one stays 1 → 2 normalized total."""
    engine = MergeRuleEngine()
    service = LabelNormalizationService(merge_rule_engine=engine)
    raw_labels = [
        _raw("r1", group_key="g1", sku_raw="SKU-A"),
        _raw("r2", group_key="g1", sku_raw="SKU-A"),
        _raw("r3", group_key="g2", sku_raw="SKU-B"),
    ]
    normalized = service.normalize(raw_labels)
    assert len(normalized) == 2
    merged = [n for n in normalized if len(n.raw_label_ids) > 1]
    single = [n for n in normalized if len(n.raw_label_ids) == 1]
    assert len(merged) == 1 and len(merged[0].raw_label_ids) == 2
    assert len(single) == 1
