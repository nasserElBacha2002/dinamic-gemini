"""Unit tests for FinalCountBuilder — v3.2.3."""

from datetime import datetime, timezone

import pytest

from src.application.services.final_count_builder import FinalCountBuilder
from src.domain.labels.entities import NormalizedLabel


def _nl(
    id_: str,
    position_id: str = "pos1",
    canonical_sku: str = "SKU-A",
    review_required: bool = False,
    merge_rule: str = "same_sku_same_group",
) -> NormalizedLabel:
    return NormalizedLabel(
        id=id_,
        inventory_id="inv1",
        aisle_id="aisle1",
        position_id=position_id,
        group_key="g1",
        canonical_sku=canonical_sku,
        canonical_product_name=None,
        raw_label_ids=[id_],
        merge_rule_applied=merge_rule,
        merge_confidence=0.9,
        merge_reason="test",
        review_required=review_required,
        metadata={},
        created_at=datetime.now(timezone.utc),
    )


def test_quantity_from_normalized_count():
    """Quantity = count of normalized labels per (position, sku)."""
    builder = FinalCountBuilder()
    normalized = [
        _nl("n1", position_id="pos1", canonical_sku="SKU-A"),
        _nl("n2", position_id="pos1", canonical_sku="SKU-A"),
    ]
    records = builder.build(normalized)
    assert len(records) == 1
    assert records[0].quantity == 2
    assert records[0].sku == "SKU-A"
    assert records[0].position_id == "pos1"
    assert set(records[0].normalized_label_ids) == {"n1", "n2"}


def test_multiple_positions():
    """Different positions → separate final count records."""
    builder = FinalCountBuilder()
    normalized = [
        _nl("n1", position_id="pos1", canonical_sku="SKU-A"),
        _nl("n2", position_id="pos2", canonical_sku="SKU-A"),
    ]
    records = builder.build(normalized)
    assert len(records) == 2
    by_pos = {r.position_id: r for r in records}
    assert by_pos["pos1"].quantity == 1 and by_pos["pos2"].quantity == 1


def test_review_required_propagated():
    """If any normalized has review_required, final record has it."""
    builder = FinalCountBuilder()
    normalized = [
        _nl("n1", review_required=False),
        _nl("n2", review_required=True),
    ]
    records = builder.build(normalized)
    assert len(records) == 1
    assert records[0].review_required is True


def test_explanation_summary():
    """explanation_summary is generated."""
    builder = FinalCountBuilder()
    normalized = [_nl("n1")]
    records = builder.build(normalized)
    assert len(records) == 1
    assert records[0].explanation_summary is not None
    assert "normalized" in records[0].explanation_summary.lower() or "1" in records[0].explanation_summary
