"""API tests for aisle code scan routes (Phase 1)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from src.api.dependencies import (
    get_code_scanner,
    get_list_aisle_code_scans_use_case,
    get_run_aisle_code_scan_use_case,
    get_summarize_aisle_code_scans_use_case,
)
from src.api.errors import mapped_http_exception
from src.api.errors.structured_api_http import CODE_SCAN_SCANNER_UNAVAILABLE
from src.api.server import app
from src.application.errors import (
    AisleNotFoundError,
    CodeScanScannerUnavailableError,
    NoSourceAssetsForCodeScanError,
)
from src.application.ports.code_scan_repository import CodeScanSummaryItem
from src.application.use_cases.list_aisle_code_scans import (
    ListAisleCodeScansCommand,
    ListAisleCodeScansResult,
)
from src.application.use_cases.run_aisle_code_scan import (
    RunAisleCodeScanCommand,
    RunAisleCodeScanResult,
)
from src.application.use_cases.summarize_aisle_code_scans import (
    SummarizeAisleCodeScansCommand,
    SummarizeAisleCodeScansResult,
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
from src.domain.code_scans.matching import CodeScanMatchStatus


def _fake_admin() -> AuthUser:
    return AuthUser(id="admin", username="admin", role="administrator")


def test_post_run_passes_created_by_from_admin() -> None:
    captured: list[RunAisleCodeScanCommand] = []

    class StubRun:
        def execute(self, cmd: RunAisleCodeScanCommand) -> RunAisleCodeScanResult:
            captured.append(cmd)
            now = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
            return RunAisleCodeScanResult(
                run_id="run-1",
                status=CodeScanRunStatus.COMPLETED,
                total_assets=0,
                processed_assets=0,
                failed_assets=0,
                total_codes_found=0,
                total_qr_found=0,
                total_barcodes_found=0,
                warnings=(),
                started_at=now,
                finished_at=now,
                scanner_engine="noop",
            )

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_run_aisle_code_scan_use_case] = lambda: StubRun()
    try:
        client = TestClient(app)
        resp = client.post("/api/v3/inventories/inv1/aisles/a1/code-scans/run")
        assert resp.status_code == 200
        assert len(captured) == 1
        assert captured[0].created_by == "admin"
    finally:
        app.dependency_overrides.clear()


def test_code_scan_scanner_unavailable_maps_to_503() -> None:
    exc = CodeScanScannerUnavailableError("Code scan engine is unavailable")
    mapped = mapped_http_exception(exc)
    assert mapped is not None
    assert mapped.status_code == 503
    assert mapped.error_code == CODE_SCAN_SCANNER_UNAVAILABLE


def test_post_run_scanner_unavailable_dependency_returns_503() -> None:
    def failing_scanner():
        exc = CodeScanScannerUnavailableError("Code scan engine is unavailable")
        mapped = mapped_http_exception(exc)
        assert mapped is not None
        raise mapped

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_code_scanner] = failing_scanner
    try:
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/v3/inventories/inv1/aisles/a1/code-scans/run")
        assert resp.status_code == 503
        body = resp.json()
        assert body.get("code") == CODE_SCAN_SCANNER_UNAVAILABLE
    finally:
        app.dependency_overrides.clear()


def test_post_run_unexpected_failure_returns_500() -> None:
    class StubRun:
        def execute(self, _cmd: RunAisleCodeScanCommand) -> RunAisleCodeScanResult:
            raise RuntimeError("unexpected infra failure")

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_run_aisle_code_scan_use_case] = lambda: StubRun()
    try:
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/v3/inventories/inv1/aisles/a1/code-scans/run")
        assert resp.status_code == 500
    finally:
        app.dependency_overrides.clear()


def test_post_run_returns_summary() -> None:
    now = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)

    class StubRun:
        def execute(self, _cmd: RunAisleCodeScanCommand) -> RunAisleCodeScanResult:
            return RunAisleCodeScanResult(
                run_id="run-1",
                status=CodeScanRunStatus.COMPLETED,
                total_assets=2,
                processed_assets=2,
                failed_assets=0,
                total_codes_found=1,
                total_qr_found=0,
                total_barcodes_found=1,
                warnings=(),
                started_at=now,
                finished_at=now,
                scanner_engine="noop",
            )

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_run_aisle_code_scan_use_case] = lambda: StubRun()
    try:
        client = TestClient(app)
        resp = client.post("/api/v3/inventories/inv1/aisles/a1/code-scans/run")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run"]["id"] == "run-1"
        assert data["run"]["status"] == "completed"
        assert data["run"]["total_codes_found"] == 1
    finally:
        app.dependency_overrides.clear()


def test_get_list_includes_match_fields() -> None:
    now = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
    run = CodeScanRun(
        id="run-1",
        inventory_id="inv1",
        aisle_id="a1",
        status=CodeScanRunStatus.COMPLETED,
        total_assets=1,
        processed_assets=1,
        failed_assets=0,
        total_codes_found=1,
        total_qr_found=0,
        total_barcodes_found=1,
        started_at=now,
        finished_at=now,
        scanner_engine="noop",
        is_latest=True,
    )
    detection = CodeScanDetection(
        id="det-1",
        run_id="run-1",
        inventory_id="inv1",
        aisle_id="a1",
        asset_id="asset-1",
        code_type=CodeType.BARCODE,
        code_value="3075807",
        normalized_code_value="3075807",
        detection_status=CodeScanDetectionStatus.DETECTED,
        scanner_engine="noop",
        created_at=now,
        matched_position_id="pos-1",
        match_status=CodeScanMatchStatus.MATCHED.value,
        match_type="sku_exact",
        match_confidence=1.0,
        matched_at=now,
    )

    class StubList:
        def execute(self, _cmd: ListAisleCodeScansCommand) -> ListAisleCodeScansResult:
            return ListAisleCodeScansResult(latest_run=run, detections=(detection,))

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_list_aisle_code_scans_use_case] = lambda: StubList()
    try:
        client = TestClient(app)
        resp = client.get("/api/v3/inventories/inv1/aisles/a1/code-scans")
        assert resp.status_code == 200
        row = resp.json()["detections"][0]
        assert row["match_status"] == "matched"
        assert row["matched_position_id"] == "pos-1"
        assert row["match_type"] == "sku_exact"
    finally:
        app.dependency_overrides.clear()


def test_get_list_empty_latest_run() -> None:
    class StubList:
        def execute(self, _cmd: ListAisleCodeScansCommand) -> ListAisleCodeScansResult:
            return ListAisleCodeScansResult(latest_run=None, detections=())

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_list_aisle_code_scans_use_case] = lambda: StubList()
    try:
        client = TestClient(app)
        resp = client.get("/api/v3/inventories/inv1/aisles/a1/code-scans")
        assert resp.status_code == 200
        data = resp.json()
        assert data["latest_run"] is None
        assert data["detections"] == []
    finally:
        app.dependency_overrides.clear()


def test_get_summary_groups() -> None:
    now = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)

    class StubSummary:
        def execute(self, _cmd: SummarizeAisleCodeScansCommand) -> SummarizeAisleCodeScansResult:
            return SummarizeAisleCodeScansResult(
                latest_run=None,
                items=(
                    CodeScanSummaryItem(
                        code_value="3075807",
                        normalized_code_value="3075807",
                        code_type="barcode",
                        occurrences=3,
                        asset_ids=("a1", "a2"),
                        first_seen_at=now,
                    ),
                ),
            )

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_summarize_aisle_code_scans_use_case] = lambda: StubSummary()
    try:
        client = TestClient(app)
        resp = client.get("/api/v3/inventories/inv1/aisles/a1/code-scans/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["occurrences"] == 3
        assert data["items"][0]["asset_ids"] == ["a1", "a2"]
    finally:
        app.dependency_overrides.clear()


def test_post_run_maps_no_assets_to_409() -> None:
    class StubRun:
        def execute(self, _cmd: RunAisleCodeScanCommand) -> RunAisleCodeScanResult:
            raise NoSourceAssetsForCodeScanError("no assets")

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_run_aisle_code_scan_use_case] = lambda: StubRun()
    try:
        client = TestClient(app)
        resp = client.post("/api/v3/inventories/inv1/aisles/a1/code-scans/run")
        assert resp.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_get_list_maps_aisle_not_found() -> None:
    class StubList:
        def execute(self, _cmd: ListAisleCodeScansCommand) -> ListAisleCodeScansResult:
            raise AisleNotFoundError("Aisle not found: a1")

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_list_aisle_code_scans_use_case] = lambda: StubList()
    try:
        client = TestClient(app)
        resp = client.get("/api/v3/inventories/inv1/aisles/a1/code-scans")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()
