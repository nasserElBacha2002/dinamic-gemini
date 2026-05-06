from src.domain.quantity.resolution import (
    QtyInferenceReason,
    QtyParseStatus,
    QtySource,
    normalize_raw_qty,
    resolve_final_qty,
)


def test_valid_evidence_missing_qty_infers_one() -> None:
    normalized = normalize_raw_qty(None, field_was_present=False)
    res = resolve_final_qty(
        has_valid_evidence=True,
        is_product_present=True,
        normalized_qty=normalized,
    )
    assert res.qty_final == 1
    assert res.qty_source == QtySource.INFERRED
    assert res.qty_inference_reason == QtyInferenceReason.VALID_EVIDENCE_WITHOUT_EXPLICIT_QUANTITY
    assert res.qty_parse_status == QtyParseStatus.MISSING
    assert res.is_resolved is True


def test_valid_evidence_null_qty_infers_one() -> None:
    normalized = normalize_raw_qty(None, field_was_present=True)
    res = resolve_final_qty(
        has_valid_evidence=True,
        is_product_present=True,
        normalized_qty=normalized,
    )
    assert res.qty_final == 1
    assert res.qty_source == QtySource.INFERRED
    assert res.qty_inference_reason == QtyInferenceReason.VALID_EVIDENCE_WITHOUT_EXPLICIT_QUANTITY
    assert res.qty_parse_status == QtyParseStatus.NULL


def test_valid_evidence_zero_qty_infers_one_when_zero_not_allowed() -> None:
    normalized = normalize_raw_qty(0, field_was_present=True)
    res = resolve_final_qty(
        has_valid_evidence=True,
        is_product_present=True,
        normalized_qty=normalized,
        allow_zero_as_valid=False,
    )
    assert res.qty_final == 1
    assert res.qty_source == QtySource.INFERRED
    assert res.qty_inference_reason == QtyInferenceReason.VALID_EVIDENCE_WITHOUT_EXPLICIT_QUANTITY
    assert res.qty_parse_status == QtyParseStatus.ZERO


def test_explicit_qty_wins_over_inference() -> None:
    normalized = normalize_raw_qty(2, field_was_present=True)
    res = resolve_final_qty(
        has_valid_evidence=True,
        is_product_present=True,
        normalized_qty=normalized,
    )
    assert res.qty_final == 2
    assert res.qty_source == QtySource.DETECTED
    assert res.qty_inference_reason is None


def test_invalid_evidence_no_inference() -> None:
    normalized = normalize_raw_qty(None, field_was_present=True)
    res = resolve_final_qty(
        has_valid_evidence=False,
        is_product_present=True,
        normalized_qty=normalized,
    )
    assert res.qty_final == 0
    assert res.qty_source == QtySource.DETECTED
    assert res.qty_inference_reason is None
    assert res.is_resolved is False


def test_explicit_consolidated_qty_wins_when_no_explicit_detected() -> None:
    normalized = normalize_raw_qty(None, field_was_present=True)
    res = resolve_final_qty(
        has_valid_evidence=True,
        is_product_present=True,
        normalized_qty=normalized,
        explicit_consolidated_qty=4,
    )
    assert res.qty_final == 4
    assert res.qty_source == QtySource.CONSOLIDATED
    assert res.qty_inference_reason is None


def test_zero_preserved_only_when_allowed() -> None:
    normalized = normalize_raw_qty(0, field_was_present=True)
    res = resolve_final_qty(
        has_valid_evidence=True,
        is_product_present=True,
        normalized_qty=normalized,
        allow_zero_as_valid=True,
    )
    assert res.qty_final == 0
    assert res.qty_source == QtySource.DETECTED
    assert res.qty_inference_reason is None
    assert res.is_resolved is True


def test_unresolved_path_cannot_leak_as_valid_qty_zero() -> None:
    """Unresolved (insufficient evidence / not product-present) returns is_resolved=False so qty_final=0 is not treated as valid visible."""
    normalized = normalize_raw_qty(None, field_was_present=False)
    res = resolve_final_qty(
        has_valid_evidence=False,
        is_product_present=True,
        normalized_qty=normalized,
    )
    assert res.is_resolved is False
    assert res.qty_final == 0
