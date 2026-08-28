"""Route contract tests for Dinamic Scanner TXT import (no SQL Server required)."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import (
    get_confirm_dinamic_scanner_txt_import_use_case,
    get_preview_dinamic_scanner_txt_import_use_case,
    require_inventory_client_scope,
)
from src.api.server import app
from src.application.dto.access_principal import AccessPrincipal
from src.application.use_cases.inventories.manage_dinamic_scanner_txt_import import (
    DinamicScannerTxtConfirmResult,
    DinamicScannerTxtPreviewResult,
)
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.domain.local_csv_import.entities import LocalCsvImport

client = TestClient(app)


def _auth_override() -> AccessPrincipal:
    return AccessPrincipal(
        actor_id="test-user",
        client_id="client-1",
        roles=frozenset({"administrator"}),
        is_platform=True,
    )


def _preview_result(*, inventory_id: str) -> DinamicScannerTxtPreviewResult:
    ts = datetime.now(timezone.utc)
    csv_import = LocalCsvImport(
        id="import-1",
        export_id="scanner-txt-abc",
        schema_version="1.1",
        inventory_id=inventory_id,
        device_id="dinamic-scanner",
        exported_at=ts,
        status="PREVIEWED",
        content_hash="sha256:abc",
        total_rows=1,
        valid_rows=1,
        rejected_rows=0,
        duplicate_rows=0,
        created_at=ts,
        updated_at=ts,
        rows=(),
        source_metadata_json='{"kind":"DINAMIC_SCANNER_TXT","aisle_code":"A1"}',
    )
    return DinamicScannerTxtPreviewResult(
        aisle_code="A1",
        aisle_id="",
        aisle_created=False,
        aisle_will_be_created=True,
        positions_imported=1,
        products_imported=1,
        omitted_records=0,
        parse_warnings=("line 9: unknown_record",),
        csv_import=csv_import,
    )


@pytest.fixture(autouse=True)
def _route_auth_override():
    app.dependency_overrides[get_current_admin] = lambda: AuthUser(
        id="admin", username="admin", role="administrator"
    )
    app.dependency_overrides[require_inventory_client_scope] = _auth_override
    yield
    app.dependency_overrides.pop(require_inventory_client_scope, None)
    app.dependency_overrides.pop(get_current_admin, None)


def test_preview_route_returns_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SERVER_DINAMIC_SCANNER_TXT_IMPORT_ENABLED", "true")
    mock_preview = MagicMock()
    mock_preview.execute.return_value = _preview_result(inventory_id="inventory-1")
    app.dependency_overrides[get_preview_dinamic_scanner_txt_import_use_case] = lambda: mock_preview

    try:
        response = client.post(
            "/api/v3/inventories/inventory-1/dinamic-scanner-txt-imports/preview",
            files={"file": ("A1.txt", BytesIO(b"POSITION|P|01|RIGHT\nD1|L|SKU|1|X"), "text/plain")},
        )
    finally:
        app.dependency_overrides.pop(get_preview_dinamic_scanner_txt_import_use_case, None)

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["aisle_will_be_created"] is True
    assert data["parse_warnings"] == ["line 9: unknown_record"]


def test_preview_route_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SERVER_DINAMIC_SCANNER_TXT_IMPORT_ENABLED", "false")
    response = client.post(
        "/api/v3/inventories/inventory-1/dinamic-scanner-txt-imports/preview",
        files={"file": ("A1.txt", BytesIO(b"POSITION|P|01|RIGHT\n"), "text/plain")},
    )
    assert response.status_code == 404


def test_confirm_route_returns_persisted_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SERVER_DINAMIC_SCANNER_TXT_IMPORT_ENABLED", "true")
    preview = _preview_result(inventory_id="inventory-1")
    confirm_result = DinamicScannerTxtConfirmResult(
        aisle_code=preview.aisle_code,
        aisle_id="aisle-1",
        aisle_created=True,
        aisle_will_be_created=True,
        positions_imported=1,
        products_imported=1,
        omitted_records=0,
        parse_warnings=preview.parse_warnings,
        csv_import=preview.csv_import,
        duplicate=False,
    )
    mock_confirm = MagicMock()
    mock_confirm.execute.return_value = confirm_result
    app.dependency_overrides[get_confirm_dinamic_scanner_txt_import_use_case] = lambda: mock_confirm

    try:
        response = client.post(
            "/api/v3/inventories/inventory-1/dinamic-scanner-txt-imports/confirm",
            json={"export_id": "scanner-txt-abc", "conflict_policy": "SKIP"},
        )
    finally:
        app.dependency_overrides.pop(get_confirm_dinamic_scanner_txt_import_use_case, None)

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["aisle_created"] is True
    assert data["parse_warnings"] == ["line 9: unknown_record"]
