"""Lightweight API wiring tests for v3 clients endpoints."""

from fastapi.testclient import TestClient

from src.api.server import app

client = TestClient(app)


def test_post_clients_returns_201_and_entity() -> None:
    response = client.post("/api/v3/clients", json={"name": "Retail A"})
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Retail A"
    assert data["status"] == "active"
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


def test_post_clients_empty_name_returns_422() -> None:
    response = client.post("/api/v3/clients", json={"name": ""})
    assert response.status_code == 422


def test_get_client_success_and_not_found() -> None:
    created = client.post("/api/v3/clients", json={"name": "Retail B"})
    assert created.status_code == 201
    cid = created.json()["id"]

    get_ok = client.get(f"/api/v3/clients/{cid}")
    assert get_ok.status_code == 200
    assert get_ok.json()["id"] == cid

    missing = client.get("/api/v3/clients/nonexistent-client")
    assert missing.status_code == 404
    payload = missing.json()
    assert payload.get("detail") == "Client not found"
    assert payload.get("code") == "CLIENT_NOT_FOUND"


def test_list_clients_response_shape() -> None:
    client.post("/api/v3/clients", json={"name": "Retail C"})
    response = client.get("/api/v3/clients?page=1&page_size=10")
    assert response.status_code == 200
    data = response.json()
    assert {"items", "page", "page_size", "total_items", "total_pages"} <= set(data.keys())
    assert isinstance(data["items"], list)

