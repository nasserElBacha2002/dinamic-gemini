"""Use case tests for aisle code scan review signals (Phase 6A)."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.use_cases.code_scans.get_aisle_code_scan_review_signals import (
    GetAisleCodeScanReviewSignalsCommand,
    GetAisleCodeScanReviewSignalsUseCase,
)
from src.domain.code_scans.entities import (
    CodeScanDetection,
    CodeScanDetectionStatus,
    CodeScanRun,
    CodeScanRunStatus,
    CodeType,
)
from src.domain.code_scans.matching import CodeScanMatchStatus
from src.infrastructure.repositories.memory_code_scan_repository import MemoryCodeScanRepository
from tests.application.use_cases.test_run_aisle_code_scan import StubAisleRepo, _aisle

NOW = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)


def _run() -> CodeScanRun:
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
    )


def _det() -> CodeScanDetection:
    return CodeScanDetection(
        id="det-1",
        run_id="run-1",
        inventory_id="inv-1",
        aisle_id="aisle-1",
        asset_id="asset-1",
        code_type=CodeType.BARCODE,
        code_value="7791234567890",
        normalized_code_value="7791234567890",
        detection_status=CodeScanDetectionStatus.DETECTED,
        scanner_engine="pyzbar",
        created_at=NOW,
        match_status=CodeScanMatchStatus.NO_MATCH.value,
    )


def test_empty_when_no_run() -> None:
    uc = GetAisleCodeScanReviewSignalsUseCase(
        aisle_repo=StubAisleRepo(_aisle()),
        code_scan_repo=MemoryCodeScanRepository(),
    )
    result = uc.execute(GetAisleCodeScanReviewSignalsCommand("inv-1", "aisle-1"))
    assert result.latest_run is None
    assert result.signals == ()
    assert result.summary.total_signals == 0


def test_returns_signals_without_mutation() -> None:
    repo = MemoryCodeScanRepository()
    repo.save_run(_run())
    repo.save_detections([_det()])
    uc = GetAisleCodeScanReviewSignalsUseCase(
        aisle_repo=StubAisleRepo(_aisle()),
        code_scan_repo=repo,
    )
    result = uc.execute(GetAisleCodeScanReviewSignalsCommand("inv-1", "aisle-1"))
    assert result.latest_run is not None
    assert len(result.signals) >= 1
    assert result.summary.unmatched_codes == 1
