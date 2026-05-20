"""Tests for SummarizeAisleCodeScansUseCase."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.use_cases.summarize_aisle_code_scans import (
    SummarizeAisleCodeScansCommand,
    SummarizeAisleCodeScansUseCase,
)
from src.domain.code_scans.entities import (
    CodeScanDetection,
    CodeScanDetectionStatus,
    CodeScanRun,
    CodeScanRunStatus,
    CodeType,
)
from src.infrastructure.repositories.memory_code_scan_repository import MemoryCodeScanRepository
from tests.application.use_cases.test_run_aisle_code_scan import StubAisleRepo, _aisle


def test_summarize_groups_repeated_codes() -> None:
    now = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
    repo = MemoryCodeScanRepository()
    run = CodeScanRun(
        id="run-1",
        inventory_id="inv-1",
        aisle_id="aisle-1",
        status=CodeScanRunStatus.COMPLETED,
        total_assets=2,
        processed_assets=2,
        failed_assets=0,
        total_codes_found=3,
        total_qr_found=0,
        total_barcodes_found=3,
        started_at=now,
        finished_at=now,
        scanner_engine="fake",
        is_latest=True,
    )
    repo.create_run(run)
    repo.save_detections(
        [
            CodeScanDetection(
                id="d1",
                run_id="run-1",
                inventory_id="inv-1",
                aisle_id="aisle-1",
                asset_id="asset-1",
                code_type=CodeType.BARCODE,
                code_value="3075807",
                normalized_code_value="3075807",
                detection_status=CodeScanDetectionStatus.DETECTED,
                scanner_engine="fake",
                created_at=now,
            ),
            CodeScanDetection(
                id="d2",
                run_id="run-1",
                inventory_id="inv-1",
                aisle_id="aisle-1",
                asset_id="asset-2",
                code_type=CodeType.BARCODE,
                code_value="3075807",
                normalized_code_value="3075807",
                detection_status=CodeScanDetectionStatus.DETECTED,
                scanner_engine="fake",
                created_at=now,
            ),
            CodeScanDetection(
                id="d3",
                run_id="run-1",
                inventory_id="inv-1",
                aisle_id="aisle-1",
                asset_id="asset-3",
                code_type=CodeType.QR,
                code_value="QR-X",
                normalized_code_value="QR-X",
                detection_status=CodeScanDetectionStatus.DETECTED,
                scanner_engine="fake",
                created_at=now,
            ),
        ]
    )
    uc = SummarizeAisleCodeScansUseCase(aisle_repo=StubAisleRepo(_aisle()), code_scan_repo=repo)
    result = uc.execute(SummarizeAisleCodeScansCommand(inventory_id="inv-1", aisle_id="aisle-1"))
    assert result.latest_run is not None
    assert len(result.items) == 2
    barcode = next(i for i in result.items if i.code_type == "barcode")
    assert barcode.occurrences == 2
    assert set(barcode.asset_ids) == {"asset-1", "asset-2"}


def test_summarize_empty_when_no_run() -> None:
    repo = MemoryCodeScanRepository()
    uc = SummarizeAisleCodeScansUseCase(aisle_repo=StubAisleRepo(_aisle()), code_scan_repo=repo)
    result = uc.execute(SummarizeAisleCodeScansCommand(inventory_id="inv-1", aisle_id="aisle-1"))
    assert result.latest_run is None
    assert result.items == ()
