"""Tests for code scan review signal builder (Phase 6A)."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.services.code_scan_review_signals import (
    build_review_signals,
    summarize_signals,
)
from src.domain.code_scans.entities import (
    CodeScanDetection,
    CodeScanDetectionStatus,
    CodeScanRun,
    CodeScanRunStatus,
    CodeType,
)
from src.domain.code_scans.matching import CodeScanMatchStatus
from src.domain.code_scans.signals import CodeScanSignalSeverity, CodeScanSignalType

NOW = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)


def _run(*, metadata: dict | None = None) -> CodeScanRun:
    return CodeScanRun(
        id="run-1",
        inventory_id="inv-1",
        aisle_id="aisle-1",
        status=CodeScanRunStatus.COMPLETED,
        is_latest=True,
        total_assets=1,
        processed_assets=1,
        failed_assets=0,
        total_codes_found=1,
        total_qr_found=0,
        total_barcodes_found=1,
        started_at=NOW,
        finished_at=NOW,
        scanner_engine="pyzbar",
        created_by="admin",
        metadata_json=metadata,
    )


def _det(
    det_id: str,
    *,
    match_status: str | None = None,
    matched_position_id: str | None = None,
) -> CodeScanDetection:
    return CodeScanDetection(
        id=det_id,
        run_id="run-1",
        inventory_id="inv-1",
        aisle_id="aisle-1",
        asset_id=f"asset-{det_id}",
        code_type=CodeType.BARCODE,
        code_value="7791234567890",
        normalized_code_value="7791234567890",
        detection_status=CodeScanDetectionStatus.DETECTED,
        scanner_engine="pyzbar",
        created_at=NOW,
        match_status=match_status,
        matched_position_id=matched_position_id,
    )


def test_no_run_returns_empty() -> None:
    assert build_review_signals(detections=(), latest_run=None) == ()


def test_code_no_match_signal() -> None:
    signals = build_review_signals(
        detections=(_det("d1", match_status=CodeScanMatchStatus.NO_MATCH.value),),
        latest_run=_run(),
    )
    assert any(s.type == CodeScanSignalType.CODE_NO_MATCH.value for s in signals)
    assert any(s.severity == CodeScanSignalSeverity.ATTENTION.value for s in signals)


def test_multiple_candidates_signal() -> None:
    signals = build_review_signals(
        detections=(
            _det("d1", match_status=CodeScanMatchStatus.MULTIPLE_CANDIDATES.value),
        ),
        latest_run=_run(),
    )
    assert any(s.type == CodeScanSignalType.CODE_MULTIPLE_CANDIDATES.value for s in signals)


def test_result_has_code_evidence_signal() -> None:
    signals = build_review_signals(
        detections=(
            _det(
                "d1",
                match_status=CodeScanMatchStatus.MATCHED.value,
                matched_position_id="pos-1",
            ),
        ),
        latest_run=_run(),
    )
    assert any(s.type == CodeScanSignalType.RESULT_HAS_CODE_EVIDENCE.value for s in signals)
    assert any(s.position_id == "pos-1" for s in signals)


def test_matching_skipped_aisle_signal() -> None:
    signals = build_review_signals(
        detections=(_det("d1", match_status=CodeScanMatchStatus.NOT_EVALUATED.value),),
        latest_run=_run(metadata={"matching": {"status": "skipped", "attempted": False}}),
    )
    assert any(s.type == CodeScanSignalType.MATCHING_NOT_EVALUATED.value for s in signals)


def test_summary_counts_from_detections() -> None:
    dets = (
        _det("d1", match_status=CodeScanMatchStatus.MATCHED.value, matched_position_id="p1"),
        _det("d2", match_status=CodeScanMatchStatus.NO_MATCH.value),
        _det("d3", match_status=CodeScanMatchStatus.NO_MATCH.value),
    )
    signals = build_review_signals(detections=dets, latest_run=_run())
    summary = summarize_signals(signals, detections=dets)
    assert summary.matched_codes == 1
    assert summary.unmatched_codes == 2
