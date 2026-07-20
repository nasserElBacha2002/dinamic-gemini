"""Confidence normalization and ranking boundary tests."""

from __future__ import annotations

import pytest

from src.application.services.image_processing.ocr_candidate_ranker import (
    DEFAULT_AMBIGUITY_MARGIN,
    normalize_code_value,
    normalize_confidence,
    rank_code_candidates,
    score_field_candidate,
)
from src.application.services.image_processing.profile_aware_processing_result_validator import (
    FieldCandidate,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, 0.0),
        (0, 0.0),
        (1, 1.0),
        (0.5, 0.5),
        (50, 0.5),
        (100, 1.0),
        (-1, 0.0),
        (150, 1.0),
    ],
)
def test_normalize_confidence_boundaries(raw, expected) -> None:
    assert normalize_confidence(raw) == pytest.approx(expected)


def _cand(
    value: str,
    score: float | None,
    *,
    method: str = "LABELED_EXACT",
    anchor: str | None = "COD",
    labeled: bool = True,
) -> FieldCandidate:
    return FieldCandidate(
        source_key="INTERNAL_CODE",
        value=value,
        evidence_score=score if score is not None else 0.0,
        labeled=labeled,
        extraction_method=method,
        anchor_text=anchor,
    )


def test_rank_tie_and_exact_margin() -> None:
    a = _cand("1111111", 0.9)
    b = _cand("2222222", 0.9)
    tied = rank_code_candidates([a, b], ambiguity_margin=DEFAULT_AMBIGUITY_MARGIN)
    assert tied.ambiguous is True
    assert tied.winner is None

    winner = _cand("1111111", 0.90)
    runner = _cand("2222222", 0.90 - DEFAULT_AMBIGUITY_MARGIN)
    exact = rank_code_candidates(
        [runner, winner], ambiguity_margin=DEFAULT_AMBIGUITY_MARGIN
    )
    # difference == margin → not ambiguous (< margin is ambiguous)
    assert exact.ambiguous is False
    assert exact.winner is not None
    assert normalize_code_value(exact.winner.value) == "1111111"


def test_rank_null_confidence_and_scales() -> None:
    null_conf = FieldCandidate(
        source_key="INTERNAL_CODE",
        value="1111111",
        evidence_score=0.0,
        labeled=True,
        extraction_method="LABELED_EXACT",
        anchor_text="COD",
    )
    # evidence_score is float on FieldCandidate; simulate 0–100 via normalize path
    high = _cand("2222222", normalize_confidence(100), method="LABELED_EXACT")
    low = _cand("1111111", normalize_confidence(50), method="NUMERIC_PATTERN", labeled=False, anchor=None)
    decision = rank_code_candidates([low, high, null_conf])
    assert decision.winner is not None
    assert normalize_code_value(decision.winner.value) == "2222222"


def test_rank_input_order_independent_and_whitespace_equivalent() -> None:
    a = _cand("123 4567", 0.8)
    b = _cand("1234567", 0.7)
    d1 = rank_code_candidates([a, b])
    d2 = rank_code_candidates([b, a])
    assert d1.winner is not None and d2.winner is not None
    assert normalize_code_value(d1.winner.value) == normalize_code_value(d2.winner.value)


def test_anchored_outranks_unanchored_same_confidence() -> None:
    anchored = _cand("1111111", 0.7, method="LABELED_EXACT", anchor="COD", labeled=True)
    unanchored = _cand(
        "2222222", 0.7, method="NUMERIC_PATTERN", anchor=None, labeled=False
    )
    assert score_field_candidate(anchored) > score_field_candidate(unanchored)
    decision = rank_code_candidates([unanchored, anchored])
    assert decision.winner is not None
    assert normalize_code_value(decision.winner.value) == "1111111"
