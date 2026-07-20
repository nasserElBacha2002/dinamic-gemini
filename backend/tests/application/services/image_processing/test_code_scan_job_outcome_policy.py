"""Unit tests for the deterministic CODE_SCAN job outcome policy (Phase 3 corrections)."""

from __future__ import annotations

from src.application.ports.image_processing_repositories import AssetProgressCounts
from src.application.services.image_processing.code_scan_job_outcome_policy import (
    CodeScanJobOutcome,
    decide,
)


def _p(**kw: int) -> AssetProgressCounts:
    return AssetProgressCounts(**kw)


def test_cancelled_takes_precedence_over_everything() -> None:
    progress = _p(total=3, resolved=3)
    assert (
        decide(progress=progress, cancelled=True, infrastructure_error=None)
        is CodeScanJobOutcome.CANCELLED
    )


def test_infrastructure_error_is_failed() -> None:
    progress = _p(total=2, resolved=2)
    assert (
        decide(progress=progress, cancelled=False, infrastructure_error="boom")
        is CodeScanJobOutcome.FAILED
    )


def test_empty_aisle_is_succeeded() -> None:
    assert (
        decide(progress=_p(total=0), cancelled=False, infrastructure_error=None)
        is CodeScanJobOutcome.SUCCEEDED
    )


def test_all_resolved_is_succeeded() -> None:
    progress = _p(total=3, resolved=3)
    assert (
        decide(progress=progress, cancelled=False, infrastructure_error=None)
        is CodeScanJobOutcome.SUCCEEDED
    )


def test_all_unrecognized_is_succeeded() -> None:
    progress = _p(total=2, unrecognized=2)
    assert (
        decide(progress=progress, cancelled=False, infrastructure_error=None)
        is CodeScanJobOutcome.SUCCEEDED
    )


def test_all_manual_review_is_succeeded() -> None:
    progress = _p(total=2, manual_review=2)
    assert (
        decide(progress=progress, cancelled=False, infrastructure_error=None)
        is CodeScanJobOutcome.SUCCEEDED
    )


def test_all_failed_is_failed() -> None:
    progress = _p(total=3, failed=3)
    assert (
        decide(progress=progress, cancelled=False, infrastructure_error=None)
        is CodeScanJobOutcome.FAILED
    )


def test_some_failed_some_productive_is_partial() -> None:
    progress = _p(total=4, resolved=2, failed=2)
    assert (
        decide(progress=progress, cancelled=False, infrastructure_error=None)
        is CodeScanJobOutcome.PARTIALLY_COMPLETED
    )


def test_failed_plus_unrecognized_is_partial() -> None:
    progress = _p(total=3, unrecognized=2, failed=1)
    assert (
        decide(progress=progress, cancelled=False, infrastructure_error=None)
        is CodeScanJobOutcome.PARTIALLY_COMPLETED
    )


def test_pending_leftover_is_failed_inconsistency() -> None:
    progress = _p(total=3, resolved=2, pending=1)
    assert (
        decide(progress=progress, cancelled=False, infrastructure_error=None)
        is CodeScanJobOutcome.FAILED
    )


def test_processing_leftover_is_failed_inconsistency() -> None:
    progress = _p(total=3, resolved=2, processing=1)
    assert (
        decide(progress=progress, cancelled=False, infrastructure_error=None)
        is CodeScanJobOutcome.FAILED
    )
