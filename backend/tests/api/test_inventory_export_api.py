"""HTTP tests — GET /api/v3/inventories/{id}/export (CSV)."""

import csv
import io

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.application.services.csv_inventory_exporter import (
    INVENTORY_RESULTS_CSV_FIELDS,
    INVENTORY_RESULTS_TECHNICAL_CSV_FIELDS,
    UTF8_BOM,
)
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from tests.support.api_v3_test_helpers import create_test_inventory, create_test_supplier


@pytest.fixture
def client_v3() -> TestClient:
    def _fake_admin() -> AuthUser:
        return AuthUser(id="admin", username="admin", role="administrator")

    app.dependency_overrides[get_current_admin] = _fake_admin
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _parse_csv_body(raw: bytes) -> tuple[list[str], list[dict[str, str]]]:
    text = raw.decode("utf-8-sig")
    r = csv.DictReader(io.StringIO(text))
    assert r.fieldnames is not None
    return list(r.fieldnames), list(r)


def test_export_csv_success_headers_and_disposition(client_v3: TestClient) -> None:
    create = create_test_inventory(client_v3, name="Export CSV API")
    assert create.status_code == 201
    inv_id = create.json()["id"]

    resp = client_v3.get(f"/api/v3/inventories/{inv_id}/export")
    assert resp.status_code == 200
    assert "text/csv" in (resp.headers.get("content-type") or "").lower()
    assert "utf-8" in (resp.headers.get("content-type") or "").lower()
    cd = resp.headers.get("content-disposition") or ""
    assert "attachment" in cd.lower()
    assert f"inventory_{inv_id}_results.csv" in cd
    raw = resp.content
    assert raw.startswith(UTF8_BOM.encode("utf-8"))
    headers, rows = _parse_csv_body(raw)
    assert headers == list(INVENTORY_RESULTS_CSV_FIELDS)
    assert rows == []


def test_export_csv_default_format_explicit_csv(client_v3: TestClient) -> None:
    create = create_test_inventory(client_v3, name="Fmt Default")
    assert create.status_code == 201
    inv_id = create.json()["id"]

    r1 = client_v3.get(f"/api/v3/inventories/{inv_id}/export?format=csv")
    r2 = client_v3.get(f"/api/v3/inventories/{inv_id}/export")
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.content == r2.content


def test_export_csv_404_when_inventory_missing(client_v3: TestClient) -> None:
    resp = client_v3.get("/api/v3/inventories/nonexistent-inv-999/export")
    assert resp.status_code == 404
    assert resp.json().get("detail") == "Inventory not found"


def test_export_csv_422_invalid_format(client_v3: TestClient) -> None:
    create = create_test_inventory(client_v3, name="Bad Fmt")
    assert create.status_code == 201
    inv_id = create.json()["id"]
    resp = client_v3.get(f"/api/v3/inventories/{inv_id}/export?format=xlsx")
    assert resp.status_code == 422


def test_export_aisle_csv_empty_positions(client_v3: TestClient) -> None:
    """Aisle-scoped export uses same headers as inventory export; one aisle, no rows."""
    create = create_test_inventory(client_v3, name="Aisle scoped")
    assert create.status_code == 201
    inv = create.json()
    inv_id = inv["id"]
    sid = create_test_supplier(client_v3, inv["client_id"])
    aisle_resp = client_v3.post(
        f"/api/v3/inventories/{inv_id}/aisles",
        json={"code": "A1", "client_supplier_id": sid},
    )
    assert aisle_resp.status_code == 201
    aisle_id = aisle_resp.json()["id"]

    resp = client_v3.get(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/export")
    assert resp.status_code == 200
    assert "text/csv" in (resp.headers.get("content-type") or "").lower()
    cd = resp.headers.get("content-disposition") or ""
    assert f"inventory_{inv_id}_aisle_{aisle_id}_results.csv" in cd
    headers, rows = _parse_csv_body(resp.content)
    assert headers == list(INVENTORY_RESULTS_CSV_FIELDS)
    assert rows == []


def test_export_csv_headers_only_inventory_with_aisle_no_positions(client_v3: TestClient) -> None:
    create = create_test_inventory(client_v3, name="Empty positions")
    assert create.status_code == 201
    inv = create.json()
    inv_id = inv["id"]
    sid = create_test_supplier(client_v3, inv["client_id"])
    aisle_resp = client_v3.post(
        f"/api/v3/inventories/{inv_id}/aisles",
        json={"code": "A1", "client_supplier_id": sid},
    )
    assert aisle_resp.status_code == 201

    resp = client_v3.get(f"/api/v3/inventories/{inv_id}/export")
    assert resp.status_code == 200
    headers, rows = _parse_csv_body(resp.content)
    assert headers == list(INVENTORY_RESULTS_CSV_FIELDS)
    assert rows == []


def test_export_csv_technical_mode_uses_technical_headers_and_filename(
    client_v3: TestClient,
) -> None:
    create = create_test_inventory(client_v3, name="Technical export")
    assert create.status_code == 201
    inv_id = create.json()["id"]

    resp = client_v3.get(f"/api/v3/inventories/{inv_id}/export?technical=true")
    assert resp.status_code == 200
    cd = resp.headers.get("content-disposition") or ""
    assert f"inventory_{inv_id}_technical.csv" in cd
    headers, rows = _parse_csv_body(resp.content)
    assert headers == list(INVENTORY_RESULTS_TECHNICAL_CSV_FIELDS)
    assert rows == []


def test_export_inventory_summary_csv(client_v3: TestClient) -> None:
    create = create_test_inventory(client_v3, name="Summary Export")
    assert create.status_code == 201
    inv_id = create.json()["id"]
    resp = client_v3.get(f"/api/v3/inventories/{inv_id}/export/summary?level=inventory")
    assert resp.status_code == 200
    assert "text/csv" in (resp.headers.get("content-type") or "").lower()
    cd = resp.headers.get("content-disposition") or ""
    assert "Summary_Export" in cd or "summary" in cd.lower()
    assert inv_id not in cd or "inventory_Summary" in cd
    headers, rows = _parse_csv_body(resp.content)
    assert headers[0] == "Inventario"
    assert len(rows) == 1


def test_export_summary_invalid_level_422(client_v3: TestClient) -> None:
    create = create_test_inventory(client_v3, name="Bad Level")
    inv_id = create.json()["id"]
    resp = client_v3.get(f"/api/v3/inventories/{inv_id}/export/summary?level=totals")
    assert resp.status_code == 422


def test_export_aisle_invalid_profile_422(client_v3: TestClient) -> None:
    create = create_test_inventory(client_v3, name="Bad Profile")
    inv = create.json()
    inv_id = inv["id"]
    sid = create_test_supplier(client_v3, inv["client_id"])
    aisle_resp = client_v3.post(
        f"/api/v3/inventories/{inv_id}/aisles",
        json={"code": "X1", "client_supplier_id": sid},
    )
    aisle_id = aisle_resp.json()["id"]
    resp = client_v3.get(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/export?profile=enterprise"
    )
    assert resp.status_code == 422


def test_export_inventory_package_zip(client_v3: TestClient) -> None:
    import io
    import zipfile

    create = create_test_inventory(client_v3, name="Package Export")
    assert create.status_code == 201
    inv_id = create.json()["id"]
    resp = client_v3.get(f"/api/v3/inventories/{inv_id}/export/package")
    assert resp.status_code == 200
    assert "zip" in (resp.headers.get("content-type") or "").lower()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = set(zf.namelist())
    assert "inventory_summary.csv" in names
    assert "aisles_summary.csv" in names


def test_export_aisle_business_profile(client_v3: TestClient) -> None:
    create = create_test_inventory(client_v3, name="Business Aisle")
    assert create.status_code == 201
    inv = create.json()
    inv_id = inv["id"]
    sid = create_test_supplier(client_v3, inv["client_id"])
    aisle_resp = client_v3.post(
        f"/api/v3/inventories/{inv_id}/aisles",
        json={"code": "B1", "client_supplier_id": sid},
    )
    assert aisle_resp.status_code == 201
    aisle_id = aisle_resp.json()["id"]
    resp = client_v3.get(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/export?profile=business"
    )
    assert resp.status_code == 200
    headers, _ = _parse_csv_body(resp.content)
    assert headers[0] == "Inventario"
    cd = resp.headers.get("content-disposition") or ""
    assert "operational" in cd


def test_export_aisle_legacy_default_unchanged(client_v3: TestClient) -> None:
    create = create_test_inventory(client_v3, name="Legacy Default")
    assert create.status_code == 201
    inv = create.json()
    inv_id = inv["id"]
    sid = create_test_supplier(client_v3, inv["client_id"])
    aisle_resp = client_v3.post(
        f"/api/v3/inventories/{inv_id}/aisles",
        json={"code": "L1", "client_supplier_id": sid},
    )
    aisle_id = aisle_resp.json()["id"]
    resp = client_v3.get(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/export")
    assert resp.status_code == 200
    headers, _ = _parse_csv_body(resp.content)
    assert headers == list(INVENTORY_RESULTS_CSV_FIELDS)
