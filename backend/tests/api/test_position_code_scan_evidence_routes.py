"""API tests for position code scan evidence (Phase 5)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from src.api.dependencies import get_get_position_code_scan_evidence_use_case
from src.api.server import app
from src.application.errors import PositionNotFoundError
from src.application.use_cases.positions.get_position_code_scan_evidence import (
    GetPositionCodeScanEvidenceCommand,
    GetPositionCodeScanEvidenceResult,
    PositionCodeScanEvidenceSummary,
)
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.domain.code_scans.entities import (
    CodeScanDetection,
    CodeScanDetectionStatus,
    CodeScanRun,
    CodeScanRunStatus,
    CodeType,
)
from src.domain.code_scans.matching import CodeScanMatchStatus, CodeScanMatchType


def _fake_admin() -> AuthUser:
    return AuthUser(id="admin", username="admin", role="administrator")


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
        matched_position_id="pos-1",
        match_status=CodeScanMatchStatus.MATCHED,
        match_type=CodeScanMatchType.SKU_EXACT,
        match_confidence=1.0,
        matched_at=NOW,
    )


class StubEvidenceUseCase:
    execute_calls: list[GetPositionCodeScanEvidenceCommand] = []
    save_position_called = False

    def execute(self, cmd: GetPositionCodeScanEvidenceCommand) -> GetPositionCodeScanEvidenceResult:
        StubEvidenceUseCase.execute_calls.append(cmd)
        if cmd.position_id == "missing":
            raise PositionNotFoundError("missing")
        return GetPositionCodeScanEvidenceResult(
            latest_run=_run(),
            detections=(_det(),),
            summary=PositionCodeScanEvidenceSummary(
                total_detections=1,
                source_assets_count=1,
                code_types={"barcode": 1},
            ),
        )


def test_get_position_code_scan_evidence_ok() -> None:
    StubEvidenceUseCase.execute_calls = []
    stub = StubEvidenceUseCase()
    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_get_position_code_scan_evidence_use_case] = lambda: stub
    try:
        client = TestClient(app)
        url = "/api/v3/inventories/inv-1/aisles/aisle-1/positions/pos-1/code-scan-evidence"
        resp = client.get(url)
        assert resp.status_code == 200
        body = resp.json()
        assert body["latest_run"]["id"] == "run-1"
        assert body["summary"]["total_detections"] == 1
        assert len(body["detections"]) == 1
        assert body["detections"][0]["asset_id"] == "asset-1"
        assert body["detections"][0]["match_type"] == CodeScanMatchType.SKU_EXACT
        assert len(stub.execute_calls) == 1
        assert stub.execute_calls[0].position_id == "pos-1"
    finally:
        app.dependency_overrides.clear()


def test_get_position_code_scan_evidence_not_found() -> None:
    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_get_position_code_scan_evidence_use_case] = (
        lambda: StubEvidenceUseCase()
    )
    try:
        client = TestClient(app)
        resp = client.get(
            "/api/v3/inventories/inv-1/aisles/aisle-1/positions/missing/code-scan-evidence"
        )
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()
