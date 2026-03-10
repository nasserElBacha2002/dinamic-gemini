"""API wiring tests: v3 aisle endpoints and inventory get by id."""

from fastapi.testclient import TestClient

from src.api.server import app

client = TestClient(app)


def test_get_inventory_returns_200_when_found() -> None:
    create_resp = client.post("/api/v3/inventories", json={"name": "For Get"})
    assert create_resp.status_code == 201
    inv_id = create_resp.json()["id"]

    response = client.get(f"/api/v3/inventories/{inv_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == inv_id
    assert data["name"] == "For Get"
    assert "created_at" in data


def test_get_inventory_returns_404_when_not_found() -> None:
    response = client.get("/api/v3/inventories/nonexistent-id-xyz")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_post_aisle_returns_201_and_entity() -> None:
    create_resp = client.post("/api/v3/inventories", json={"name": "For Aisles"})
    assert create_resp.status_code == 201
    inv_id = create_resp.json()["id"]

    response = client.post(
        f"/api/v3/inventories/{inv_id}/aisles",
        json={"code": "A-01"},
    )
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["inventory_id"] == inv_id
    assert data["code"] == "A-01"
    assert data["status"] == "created"
    assert "created_at" in data


def test_get_aisles_returns_list_and_includes_created() -> None:
    create_resp = client.post("/api/v3/inventories", json={"name": "For List Aisles"})
    assert create_resp.status_code == 201
    inv_id = create_resp.json()["id"]
    client.post(f"/api/v3/inventories/{inv_id}/aisles", json={"code": "B-01"})

    response = client.get(f"/api/v3/inventories/{inv_id}/aisles")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    codes = [a["code"] for a in data]
    assert "B-01" in codes


def test_post_aisle_inventory_not_found_returns_404() -> None:
    response = client.post(
        "/api/v3/inventories/nonexistent-id/aisles",
        json={"code": "A-01"},
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_post_aisle_duplicate_code_returns_409() -> None:
    create_resp = client.post("/api/v3/inventories", json={"name": "Dup Test"})
    assert create_resp.status_code == 201
    inv_id = create_resp.json()["id"]
    client.post(f"/api/v3/inventories/{inv_id}/aisles", json={"code": "DUP-1"})

    response = client.post(
        f"/api/v3/inventories/{inv_id}/aisles",
        json={"code": "DUP-1"},
    )
    assert response.status_code == 409
    assert "duplicate" in response.json()["detail"].lower() or "already exists" in response.json()["detail"].lower()


def test_get_aisles_inventory_not_found_returns_404() -> None:
    response = client.get("/api/v3/inventories/nonexistent-id/aisles")
    assert response.status_code == 404


def test_post_aisle_empty_code_returns_422() -> None:
    create_resp = client.post("/api/v3/inventories", json={"name": "Val"})
    assert create_resp.status_code == 201
    inv_id = create_resp.json()["id"]

    response = client.post(
        f"/api/v3/inventories/{inv_id}/aisles",
        json={"code": ""},
    )
    assert response.status_code == 422
