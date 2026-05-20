"""Use case tests for aisle code scan CSV exports (Phase 6B)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.errors import (
    CodeScanExportNoRunError,
    CodeScanExportUnsupportedFormatError,
    CodeScanExportUnsupportedTypeError,
)
from src.application.use_cases.export_aisle_code_scans import (
    ExportAisleCodeScansCommand,
    ExportAisleCodeScansUseCase,
)
from src.application.services.code_scan_csv_exporter import (
    DETECTIONS_CSV_FIELDS,
    SUMMARY_CSV_FIELDS,
    UNMATCHED_CSV_FIELDS,
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
        total_codes_found=2,
        total_qr_found=0,
        total_barcodes_found=2,
        started_at=NOW,
        finished_at=NOW,
        scanner_engine="pyzbar",
        created_by="admin",
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
        matched_at=NOW if matched_position_id else None,
    )


def _uc(repo: MemoryCodeScanRepository | None = None) -> ExportAisleCodeScansUseCase:
    return ExportAisleCodeScansUseCase(
        aisle_repo=StubAisleRepo(_aisle()),
        code_scan_repo=repo or MemoryCodeScanRepository(),
    )


def test_export_no_run_raises() -> None:
    with pytest.raises(CodeScanExportNoRunError):
        _uc().execute(
            ExportAisleCodeScansCommand("inv-1", "aisle-1", "csv", "detections")
        )


def test_unsupported_type_and_format() -> None:
    repo = MemoryCodeScanRepository()
    repo.save_run(_run())
    uc = _uc(repo)
    with pytest.raises(CodeScanExportUnsupportedTypeError):
        uc.execute(ExportAisleCodeScansCommand("inv-1", "aisle-1", "csv", "invalid"))
    with pytest.raises(CodeScanExportUnsupportedFormatError):
        uc.execute(ExportAisleCodeScansCommand("inv-1", "aisle-1", "xlsx", "detections"))


def test_export_detections_csv_columns() -> None:
    repo = MemoryCodeScanRepository()
    repo.save_run(_run())
    repo.save_detections(
        [
            _det(
                "d1",
                match_status=CodeScanMatchStatus.MATCHED.value,
                matched_position_id="pos-1",
            )
        ]
    )
    result = _uc(repo).execute(
        ExportAisleCodeScansCommand("inv-1", "aisle-1", "csv", "detections")
    )
    header = result.body.splitlines()[0]
    for col in DETECTIONS_CSV_FIELDS:
        assert col in header
    assert "det-1" in result.body or "d1" in result.body
    assert "asset-d1" in result.body


def test_export_unmatched_filters_statuses() -> None:
    repo = MemoryCodeScanRepository()
    repo.save_run(_run())
    repo.save_detections(
        [
            _det("d1", match_status=CodeScanMatchStatus.NO_MATCH.value),
            _det(
                "d2",
                match_status=CodeScanMatchStatus.MATCHED.value,
                matched_position_id="pos-1",
            ),
            _det("d3", match_status=CodeScanMatchStatus.MULTIPLE_CANDIDATES.value),
        ]
    )
    result = _uc(repo).execute(
        ExportAisleCodeScansCommand("inv-1", "aisle-1", "csv", "unmatched")
    )
    header = result.body.splitlines()[0]
    for col in UNMATCHED_CSV_FIELDS:
        assert col in header
    assert "d1" in result.body
    assert "d3" in result.body
    lines = result.body.strip().splitlines()
    assert len(lines) == 3  # header + 2 unmatched rows


def test_export_summary_csv() -> None:
    repo = MemoryCodeScanRepository()
    repo.save_run(_run())
    repo.save_detections(
        [
            _det("d1", match_status=CodeScanMatchStatus.MATCHED.value, matched_position_id="p1"),
            _det("d2", match_status=CodeScanMatchStatus.MATCHED.value, matched_position_id="p1"),
        ]
    )
    result = _uc(repo).execute(
        ExportAisleCodeScansCommand("inv-1", "aisle-1", "csv", "summary")
    )
    header = result.body.splitlines()[0]
    for col in SUMMARY_CSV_FIELDS:
        assert col in header
    assert "occurrences" in result.body or "2" in result.body
