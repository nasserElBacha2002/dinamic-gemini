"""API wiring tests for v3 client suppliers endpoints."""

from fastapi.testclient import TestClient

from src.api.server import app

client = TestClient(app)


def test_create_supplier_success_and_get_scoped() -> None:
    c = client.post("/api/v3/clients", json={"name": "Retail A"})
    assert c.status_code == 201
    client_id = c.json()["id"]

    created = client.post(f"/api/v3/clients/{client_id}/suppliers", json={"name": "Acme"})
    assert created.status_code == 201
    supplier_id = created.json()["id"]
    assert created.json()["client_id"] == client_id

    fetched = client.get(f"/api/v3/clients/{client_id}/suppliers/{supplier_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == supplier_id


def test_create_supplier_validation_and_missing_client() -> None:
    missing = client.post("/api/v3/clients/missing/suppliers", json={"name": "Acme"})
    assert missing.status_code == 404
    assert missing.json().get("code") == "CLIENT_NOT_FOUND"

    c = client.post("/api/v3/clients", json={"name": "Retail B"})
    client_id = c.json()["id"]
    invalid = client.post(f"/api/v3/clients/{client_id}/suppliers", json={"name": ""})
    assert invalid.status_code == 422


def test_cross_client_access_and_duplicate_scope_rules() -> None:
    a = client.post("/api/v3/clients", json={"name": "A"}).json()["id"]
    b = client.post("/api/v3/clients", json={"name": "B"}).json()["id"]

    s_a = client.post(f"/api/v3/clients/{a}/suppliers", json={"name": "Shared"})
    assert s_a.status_code == 201
    supplier_id = s_a.json()["id"]

    # Duplicate under same client -> conflict
    dup_same = client.post(f"/api/v3/clients/{a}/suppliers", json={"name": "Shared"})
    assert dup_same.status_code == 409

    # Same name under different client -> allowed
    same_other = client.post(f"/api/v3/clients/{b}/suppliers", json={"name": "Shared"})
    assert same_other.status_code == 201

    # Cross-client get should be protected
    cross = client.get(f"/api/v3/clients/{b}/suppliers/{supplier_id}")
    assert cross.status_code == 404
    assert cross.json().get("code") == "CLIENT_SUPPLIER_NOT_FOUND"


def test_list_suppliers_shape() -> None:
    c = client.post("/api/v3/clients", json={"name": "Retail C"}).json()["id"]
    client.post(f"/api/v3/clients/{c}/suppliers", json={"name": "One"})
    response = client.get(f"/api/v3/clients/{c}/suppliers?page=1&page_size=10")
    assert response.status_code == 200
    data = response.json()
    assert {"items", "page", "page_size", "total_items", "total_pages"} <= set(data.keys())


def test_get_supplier_missing_id_under_existing_client_returns_supplier_not_found() -> None:
    client_id = client.post("/api/v3/clients", json={"name": "Retail D"}).json()["id"]
    response = client.get(f"/api/v3/clients/{client_id}/suppliers/missing-supplier-id")
    assert response.status_code == 404
    payload = response.json()
    assert payload.get("code") == "CLIENT_SUPPLIER_NOT_FOUND"
    assert payload.get("detail") == "Client supplier not found"

