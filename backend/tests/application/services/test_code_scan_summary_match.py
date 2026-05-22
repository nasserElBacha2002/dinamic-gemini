"""Tests for code scan summary match aggregation."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.services.code_scan_summary_match import aggregate_group_match
from src.domain.code_scans.entities import (
    CodeScanDetection,
    CodeScanDetectionStatus,
    CodeType,
)
from src.domain.code_scans.matching import CodeScanMatchStatus, CodeScanSummaryMatchStatus


def _detection(*, match_status: str | None) -> CodeScanDetection:
    now = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
    return CodeScanDetection(
        id="d",
        run_id="run-1",
        inventory_id="inv-1",
        aisle_id="aisle-1",
        asset_id="asset-1",
        code_type=CodeType.BARCODE,
        code_value="X",
        normalized_code_value="X",
        detection_status=CodeScanDetectionStatus.DETECTED,
        scanner_engine="fake",
        created_at=now,
        match_status=match_status,
    )


def test_aggregate_mixed_status_with_counts() -> None:
    status, _, _, counts = aggregate_group_match(
        [
            _detection(match_status=CodeScanMatchStatus.MATCHED.value),
            _detection(match_status=CodeScanMatchStatus.NO_MATCH.value),
        ]
    )
    assert status == CodeScanSummaryMatchStatus.MIXED
    assert counts == {"matched": 1, "no_match": 1}
