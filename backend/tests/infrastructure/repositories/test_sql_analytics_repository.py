"""Unit tests for Sprint 4 SQL analytics expressions."""

from src.infrastructure.repositories.sql_analytics_repository import (
    _aggregated_row_expr,
    _canonical_quantity_expr,
    _issue_bucket_expr,
)


def test_canonical_quantity_expr_prefers_primary_product_for_non_aggregated_rows() -> None:
    expr = _canonical_quantity_expr("p", "pr_primary")

    assert "WHEN pr_primary.id IS NOT NULL THEN" in expr
    assert "COALESCE(pr_primary.corrected_quantity, pr_primary.detected_quantity, 0)" in expr
    assert "JSON_VALUE(p.detected_summary_json, N'$.aggregated_from_ids[0]') IS NOT NULL" in expr


def test_canonical_quantity_expr_keeps_snapshot_fallback_for_aggregated_rows() -> None:
    expr = _canonical_quantity_expr("p", "pr_primary")
    aggregated_expr = _aggregated_row_expr("p")

    assert aggregated_expr in expr
    assert "JSON_VALUE(p.detected_summary_json, N'$.final_quantity')" in expr
    assert "JSON_VALUE(p.detected_summary_json, N'$.product_label_quantity')" in expr


def test_issue_bucket_expr_uses_canonical_quantity_for_quantity_zero() -> None:
    expr = _issue_bucket_expr("p")

    assert "WHEN (" in expr
    assert ") = 0 THEN N'quantity_zero'" in expr
    assert "pr_primary.corrected_quantity" in expr
    assert "pr_primary.detected_quantity" in expr
    assert "WHEN p.primary_evidence_id IS NULL" in expr
