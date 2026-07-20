"""Deterministic OCR / field-candidate ranking with None-safe scoring."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.services.image_processing.profile_aware_processing_result_validator import (
    FieldCandidate,
)

# Minimum score margin between winner and runner-up for auto-pick among distinct values.
DEFAULT_AMBIGUITY_MARGIN = 0.05

_METHOD_BONUS = {
    "LABELED_EXACT": 0.20,
    "LABELED_FUZZY": 0.12,
    "NUMERIC_PATTERN": 0.0,
}

_RELATION_BONUS = {
    "BELOW": 0.10,
    "SAME_COLUMN": 0.08,
    "RIGHT_OF": 0.06,
    "SAME_ROW": 0.04,
    "NEAR": 0.02,
}


@dataclass(frozen=True)
class RankedCodeDecision:
    winner: FieldCandidate | None
    ambiguous: bool
    distinct_values: tuple[str, ...]
    winner_score: float
    second_score: float | None


def safe_confidence(candidate: FieldCandidate) -> float:
    conf = candidate.evidence_score
    if conf is None:
        return 0.0
    try:
        return float(conf)
    except (TypeError, ValueError):
        return 0.0


def safe_distance(candidate: FieldCandidate) -> float:
    dist = candidate.normalized_distance
    if dist is None:
        return float("inf")
    try:
        return float(dist)
    except (TypeError, ValueError):
        return float("inf")


def score_field_candidate(candidate: FieldCandidate) -> float:
    """Single scoring function for code ranking (higher is better)."""
    score = safe_confidence(candidate)
    method = (candidate.extraction_method or "").upper()
    score += _METHOD_BONUS.get(method, 0.0)
    if candidate.anchor_text:
        score += 0.08
    relation = (candidate.spatial_relation or "").upper()
    score += _RELATION_BONUS.get(relation, 0.0)
    dist = safe_distance(candidate)
    if dist != float("inf"):
        score += max(0.0, 0.12 - min(dist, 0.12))
    if candidate.labeled:
        score += 0.05
    return score


def normalize_code_value(value: str | None) -> str:
    return (value or "").strip().replace(" ", "")


def dedupe_by_normalized_value(
    candidates: list[FieldCandidate],
) -> list[FieldCandidate]:
    """Keep best evidence per normalized value."""
    best: dict[str, FieldCandidate] = {}
    best_score: dict[str, float] = {}
    for cand in candidates:
        key = normalize_code_value(cand.value)
        if not key:
            continue
        sc = score_field_candidate(cand)
        if key not in best or sc > best_score[key]:
            best[key] = cand
            best_score[key] = sc
    # Stable order: descending score then value.
    return sorted(
        best.values(),
        key=lambda c: (-score_field_candidate(c), normalize_code_value(c.value)),
    )


def rank_code_candidates(
    candidates: list[FieldCandidate],
    *,
    ambiguity_margin: float = DEFAULT_AMBIGUITY_MARGIN,
) -> RankedCodeDecision:
    """Rank distinct normalized codes; mark ambiguous when margin is insufficient."""
    if not candidates:
        return RankedCodeDecision(
            winner=None,
            ambiguous=False,
            distinct_values=(),
            winner_score=0.0,
            second_score=None,
        )

    deduped = dedupe_by_normalized_value(candidates)
    if not deduped:
        return RankedCodeDecision(
            winner=None,
            ambiguous=False,
            distinct_values=(),
            winner_score=0.0,
            second_score=None,
        )

    scored = [(score_field_candidate(c), c) for c in deduped]
    scored.sort(key=lambda t: (-t[0], normalize_code_value(t[1].value)))
    values = tuple(normalize_code_value(c.value) for _, c in scored)
    winner_score, winner = scored[0]
    if len(scored) == 1:
        return RankedCodeDecision(
            winner=winner,
            ambiguous=False,
            distinct_values=values,
            winner_score=winner_score,
            second_score=None,
        )

    second_score, _ = scored[1]
    if winner_score - second_score < float(ambiguity_margin):
        return RankedCodeDecision(
            winner=None,
            ambiguous=True,
            distinct_values=values,
            winner_score=winner_score,
            second_score=second_score,
        )
    return RankedCodeDecision(
        winner=winner,
        ambiguous=False,
        distinct_values=values,
        winner_score=winner_score,
        second_score=second_score,
    )


__all__ = [
    "DEFAULT_AMBIGUITY_MARGIN",
    "RankedCodeDecision",
    "dedupe_by_normalized_value",
    "normalize_code_value",
    "rank_code_candidates",
    "safe_confidence",
    "safe_distance",
    "score_field_candidate",
]
