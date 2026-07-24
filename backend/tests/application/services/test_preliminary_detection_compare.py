"""Unit tests for preliminary vs remote comparison (Phase 5)."""

from __future__ import annotations

from src.application.services.preliminary_detection_compare import (
    OUTCOME_BOTH_UNRESOLVED,
    OUTCOME_CODE_MISMATCH,
    OUTCOME_LOCAL_AMBIGUOUS,
    OUTCOME_LOCAL_ONLY,
    OUTCOME_MATCH_CODE_AND_QUANTITY,
    OUTCOME_MATCH_CODE_BOTH_QUANTITY_MISSING,
    OUTCOME_MATCH_CODE_LOCAL_QUANTITY_MISSING,
    OUTCOME_MATCH_CODE_QUANTITY_DIFFERENT,
    OUTCOME_MATCH_CODE_REMOTE_QUANTITY_MISSING,
    OUTCOME_REMOTE_ONLY,
    LocalCompareInput,
    RemoteCompareInput,
    compare_preliminary_vs_remote,
    normalize_code,
)


def test_normalize_preserves_leading_zeros_and_no_case_fold() -> None:
    assert normalize_code(" 0123 ") == "0123"
    assert normalize_code("AbC") == "AbC"


def test_match_code_and_quantity() -> None:
    r = compare_preliminary_vs_remote(
        LocalCompareInput("RESOLVED", "ABC", 5),
        RemoteCompareInput("SUCCEEDED", "ABC", 5),
    )
    assert r.outcome == OUTCOME_MATCH_CODE_AND_QUANTITY


def test_match_both_quantity_missing() -> None:
    r = compare_preliminary_vs_remote(
        LocalCompareInput("RESOLVED", "ABC", None),
        RemoteCompareInput("SUCCEEDED", "ABC", None),
    )
    assert r.outcome == OUTCOME_MATCH_CODE_BOTH_QUANTITY_MISSING


def test_match_local_quantity_missing() -> None:
    r = compare_preliminary_vs_remote(
        LocalCompareInput("RESOLVED", "ABC", None),
        RemoteCompareInput("SUCCEEDED", "ABC", 3),
    )
    assert r.outcome == OUTCOME_MATCH_CODE_LOCAL_QUANTITY_MISSING


def test_match_remote_quantity_missing() -> None:
    r = compare_preliminary_vs_remote(
        LocalCompareInput("RESOLVED", "ABC", 3),
        RemoteCompareInput("SUCCEEDED", "ABC", None),
    )
    assert r.outcome == OUTCOME_MATCH_CODE_REMOTE_QUANTITY_MISSING


def test_quantity_different() -> None:
    r = compare_preliminary_vs_remote(
        LocalCompareInput("RESOLVED", "ABC", 2),
        RemoteCompareInput("SUCCEEDED", "ABC", 9),
    )
    assert r.outcome == OUTCOME_MATCH_CODE_QUANTITY_DIFFERENT


def test_code_mismatch_ignores_quantity() -> None:
    r = compare_preliminary_vs_remote(
        LocalCompareInput("RESOLVED", "AAA", 1),
        RemoteCompareInput("SUCCEEDED", "BBB", 1),
    )
    assert r.outcome == OUTCOME_CODE_MISMATCH


def test_local_only() -> None:
    r = compare_preliminary_vs_remote(
        LocalCompareInput("RESOLVED", "AAA", 1),
        RemoteCompareInput("UNRECOGNIZED", None, None),
    )
    assert r.outcome == OUTCOME_LOCAL_ONLY


def test_remote_only() -> None:
    r = compare_preliminary_vs_remote(
        LocalCompareInput("UNRESOLVED", None, None),
        RemoteCompareInput("SUCCEEDED", "AAA", 1),
    )
    assert r.outcome == OUTCOME_REMOTE_ONLY


def test_both_unresolved() -> None:
    r = compare_preliminary_vs_remote(
        LocalCompareInput("UNRESOLVED", None, None),
        RemoteCompareInput("UNRECOGNIZED", None, None),
    )
    assert r.outcome == OUTCOME_BOTH_UNRESOLVED


def test_local_ambiguous() -> None:
    r = compare_preliminary_vs_remote(
        LocalCompareInput("AMBIGUOUS", "A", 1, candidate_count=2),
        RemoteCompareInput("SUCCEEDED", "A", 1),
    )
    assert r.outcome == OUTCOME_LOCAL_AMBIGUOUS


def test_leading_zeros_not_equivalent() -> None:
    r = compare_preliminary_vs_remote(
        LocalCompareInput("RESOLVED", "0123", 1),
        RemoteCompareInput("SUCCEEDED", "123", 1),
    )
    assert r.outcome == OUTCOME_CODE_MISMATCH
