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


def test_post_aisle_process_returns_202_and_job_id() -> None:
    create_resp = client.post("/api/v3/inventories", json={"name": "For Process"})
    assert create_resp.status_code == 201
    inv_id = create_resp.json()["id"]
    aisle_resp = client.post(
        f"/api/v3/inventories/{inv_id}/aisles",
        json={"code": "P-01"},
    )
    assert aisle_resp.status_code == 201
    aisle_id = aisle_resp.json()["id"]

    response = client.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/process",
    )
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert len(data["job_id"]) > 0


def test_post_aisle_process_aisle_not_found_returns_404() -> None:
    create_resp = client.post("/api/v3/inventories", json={"name": "For 404"})
    assert create_resp.status_code == 201
    inv_id = create_resp.json()["id"]

    response = client.post(
        f"/api/v3/inventories/{inv_id}/aisles/nonexistent-aisle-id/process",
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_post_aisle_process_duplicate_returns_409() -> None:
    create_resp = client.post("/api/v3/inventories", json={"name": "For 409"})
    assert create_resp.status_code == 201
    inv_id = create_resp.json()["id"]
    aisle_resp = client.post(
        f"/api/v3/inventories/{inv_id}/aisles",
        json={"code": "D-01"},
    )
    assert aisle_resp.status_code == 201
    aisle_id = aisle_resp.json()["id"]

    client.post(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/process")
    response = client.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/process",
    )
    assert response.status_code == 409
    assert "active" in response.json()["detail"].lower()


def test_get_aisle_status_returns_aisle_and_latest_job() -> None:
    create_resp = client.post("/api/v3/inventories", json={"name": "For Status"})
    assert create_resp.status_code == 201
    inv_id = create_resp.json()["id"]
    aisle_resp = client.post(
        f"/api/v3/inventories/{inv_id}/aisles",
        json={"code": "S-01"},
    )
    assert aisle_resp.status_code == 201
    aisle_id = aisle_resp.json()["id"]

    response = client.get(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/status",
    )
    assert response.status_code == 200
    data = response.json()
    assert "aisle" in data
    assert data["aisle"]["id"] == aisle_id
    assert data["aisle"]["status"] == "created"
    assert "latest_job" in data
    assert data["latest_job"] is None

    client.post(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/process")
    response2 = client.get(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/status",
    )
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["latest_job"] is not None
    assert data2["latest_job"]["status"] == "queued"
    assert data2["aisle"]["status"] == "queued"


def test_get_aisle_status_not_found_returns_404() -> None:
    create_resp = client.post("/api/v3/inventories", json={"name": "For Status 404"})
    assert create_resp.status_code == 201
    inv_id = create_resp.json()["id"]

    response = client.get(
        f"/api/v3/inventories/{inv_id}/aisles/nonexistent-aisle/status",
    )
    assert response.status_code == 404


def test_list_aisles_includes_latest_job_when_present() -> None:
    create_resp = client.post("/api/v3/inventories", json={"name": "For List Job"})
    assert create_resp.status_code == 201
    inv_id = create_resp.json()["id"]
    aisle_resp = client.post(
        f"/api/v3/inventories/{inv_id}/aisles",
        json={"code": "LJ-01"},
    )
    assert aisle_resp.status_code == 201
    aisle_id = aisle_resp.json()["id"]

    list_resp = client.get(f"/api/v3/inventories/{inv_id}/aisles")
    assert list_resp.status_code == 200
    aisles = list_resp.json()
    assert len(aisles) == 1
    assert aisles[0].get("latest_job") is None

    client.post(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/process")
    list_resp2 = client.get(f"/api/v3/inventories/{inv_id}/aisles")
    assert list_resp2.status_code == 200
    aisles2 = list_resp2.json()
    assert len(aisles2) == 1
    assert aisles2[0]["latest_job"] is not None
    assert aisles2[0]["latest_job"]["status"] == "queued"
    assert aisles2[0]["status"] == "queued"
