"""Lightweight API wiring test: v3 inventories endpoints call use cases and return expected shape."""

from fastapi.testclient import TestClient

from src.api.server import app

client = TestClient(app)


def test_post_inventories_returns_201_and_entity() -> None:
    response = client.post("/api/v3/inventories", json={"name": "Test Inventory"})
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["name"] == "Test Inventory"
    assert data["status"] == "draft"


def test_get_inventories_returns_list_and_includes_created() -> None:
    create_resp = client.post("/api/v3/inventories", json={"name": "For List"})
    assert create_resp.status_code == 201
    created_id = create_resp.json()["id"]

    response = client.get("/api/v3/inventories")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    ids = [item["id"] for item in data["items"]]
    assert created_id in ids


def test_post_inventories_empty_name_returns_422() -> None:
    response = client.post("/api/v3/inventories", json={"name": ""})
    assert response.status_code == 422


def test_post_inventories_name_too_long_returns_422() -> None:
    response = client.post("/api/v3/inventories", json={"name": "x" * 256})
    assert response.status_code == 422


def test_get_aisle_asset_file_returns_404_when_asset_not_found() -> None:
    """Reference image endpoint returns 404 when aisle has no such asset."""
    create_resp = client.post("/api/v3/inventories", json={"name": "Ref Image Test"})
    assert create_resp.status_code == 201
    inv_id = create_resp.json()["id"]
    aisle_resp = client.post(f"/api/v3/inventories/{inv_id}/aisles", json={"code": "A1"})
    assert aisle_resp.status_code == 201
    aisle_id = aisle_resp.json()["id"]

    response = client.get(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets/nonexistent-asset-id/file"
    )
    assert response.status_code == 404
    assert response.json().get("detail") == "Asset not found"


def test_get_aisle_asset_image_display_url_returns_404_when_asset_not_found() -> None:
    """image-display-url matches file endpoint when asset is missing."""
    create_resp = client.post("/api/v3/inventories", json={"name": "Display URL Test"})
    assert create_resp.status_code == 201
    inv_id = create_resp.json()["id"]
    aisle_resp = client.post(f"/api/v3/inventories/{inv_id}/aisles", json={"code": "A1"})
    assert aisle_resp.status_code == 201
    aisle_id = aisle_resp.json()["id"]

    response = client.get(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets/nonexistent-asset-id/image-display-url"
    )
    assert response.status_code == 404
    assert response.json().get("detail") == "Asset not found"
