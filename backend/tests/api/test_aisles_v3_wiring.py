"""API wiring tests: v3 aisle endpoints and inventory get by id."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from src.api.server import app
from src.api.dependencies import (
    get_aisle_repo,
    get_inventory_repo,
    get_job_repo,
)
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository

client = TestClient(app)


def _fake_admin() -> AuthUser:
    return AuthUser(id="admin", username="admin", role="administrator")


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
    assert "created_at" in data2["latest_job"], "aisle status latest_job must expose created_at (Phase 2 Block 2)"
    assert data2["aisle"]["status"] == "queued"


def test_list_aisles_latest_job_includes_created_at() -> None:
    """v3.2.5 Phase 2 Block 2: GET .../aisles returns latest_job.created_at when present."""
    create_resp = client.post("/api/v3/inventories", json={"name": "For List Job CreatedAt"})
    assert create_resp.status_code == 201
    inv_id = create_resp.json()["id"]
    aisle_resp = client.post(
        f"/api/v3/inventories/{inv_id}/aisles",
        json={"code": "LJ-CA"},
    )
    assert aisle_resp.status_code == 201
    aisle_id = aisle_resp.json()["id"]
    client.post(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/process")
    list_resp = client.get(f"/api/v3/inventories/{inv_id}/aisles")
    assert list_resp.status_code == 200
    aisles = list_resp.json()
    assert len(aisles) == 1
    assert aisles[0]["latest_job"] is not None
    assert "created_at" in aisles[0]["latest_job"], "aisle list latest_job must expose created_at (Phase 2 Block 2)"


def test_list_and_status_latest_job_created_at_aligned() -> None:
    """v3.2.5 Phase 2 Block 2: list and status expose the same latest_job.created_at for the same job."""
    create_resp = client.post("/api/v3/inventories", json={"name": "For Aligned CreatedAt"})
    assert create_resp.status_code == 201
    inv_id = create_resp.json()["id"]
    aisle_resp = client.post(
        f"/api/v3/inventories/{inv_id}/aisles",
        json={"code": "AL-01"},
    )
    assert aisle_resp.status_code == 201
    aisle_id = aisle_resp.json()["id"]
    client.post(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/process")
    list_resp = client.get(f"/api/v3/inventories/{inv_id}/aisles")
    status_resp = client.get(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/status")
    assert list_resp.status_code == 200
    assert status_resp.status_code == 200
    list_data = list_resp.json()
    status_data = status_resp.json()
    assert list_data[0]["latest_job"] is not None
    assert status_data["latest_job"] is not None
    list_created = list_data[0]["latest_job"]["created_at"]
    status_created = status_data["latest_job"]["created_at"]
    assert list_created == status_created, "list and status must expose same latest_job.created_at"


def test_cancel_queued_job_returns_202_and_list_and_status_show_canceled() -> None:
    """Phase 3 Block 1 Case 1: Cancel QUEUED job -> 202; list and status expose latest_job.status = canceled."""
    create_resp = client.post("/api/v3/inventories", json={"name": "For Cancel"})
    assert create_resp.status_code == 201
    inv_id = create_resp.json()["id"]
    aisle_resp = client.post(
        f"/api/v3/inventories/{inv_id}/aisles",
        json={"code": "C-01"},
    )
    assert aisle_resp.status_code == 201
    aisle_id = aisle_resp.json()["id"]
    process_resp = client.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/process",
    )
    assert process_resp.status_code == 202
    job_id = process_resp.json()["job_id"]

    cancel_resp = client.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/jobs/{job_id}/cancel",
    )
    assert cancel_resp.status_code == 202

    list_resp = client.get(f"/api/v3/inventories/{inv_id}/aisles")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert len(list_data) == 1
    assert list_data[0]["latest_job"] is not None
    assert list_data[0]["latest_job"]["status"] == "canceled"

    status_resp = client.get(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/status",
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["latest_job"] is not None
    assert status_resp.json()["latest_job"]["status"] == "canceled"


def test_cancel_already_canceled_job_returns_409() -> None:
    """Phase 3 Block 1 Case 3: Cancel terminal (CANCELED) job -> 409."""
    create_resp = client.post("/api/v3/inventories", json={"name": "For Cancel 409"})
    assert create_resp.status_code == 201
    inv_id = create_resp.json()["id"]
    aisle_resp = client.post(
        f"/api/v3/inventories/{inv_id}/aisles",
        json={"code": "C-02"},
    )
    assert aisle_resp.status_code == 201
    aisle_id = aisle_resp.json()["id"]
    process_resp = client.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/process",
    )
    assert process_resp.status_code == 202
    job_id = process_resp.json()["job_id"]

    client.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/jobs/{job_id}/cancel",
    )
    cancel_again = client.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/jobs/{job_id}/cancel",
    )
    assert cancel_again.status_code == 409
    assert "terminal" in cancel_again.json().get("detail", "").lower() or "cancel" in cancel_again.json().get("detail", "").lower()


def test_cancel_running_job_returns_202_and_list_and_status_show_cancel_requested() -> None:
    """Phase 3 Block 1 Case 2: Cancel RUNNING job -> 202; list and status expose latest_job.status = cancel_requested."""
    now = datetime.now(timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository()

    inv = Inventory("inv-running", "For Running Cancel", InventoryStatus.DRAFT, now, now)
    inv_repo.save(inv)
    aisle = Aisle("aisle-running", "inv-running", "R-01", AisleStatus.CREATED, now, now)
    aisle_repo.save(aisle)
    job = Job(
        id="job-running",
        target_type="aisle",
        target_id="aisle-running",
        job_type="process_aisle",
        status=JobStatus.RUNNING,
        payload_json={"aisle_id": "aisle-running"},
        created_at=now,
        updated_at=now,
    )
    job_repo.save(job)

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_inventory_repo] = lambda: inv_repo
    app.dependency_overrides[get_aisle_repo] = lambda: aisle_repo
    app.dependency_overrides[get_job_repo] = lambda: job_repo
    try:
        c = TestClient(app)
        cancel_resp = c.post(
            "/api/v3/inventories/inv-running/aisles/aisle-running/jobs/job-running/cancel",
        )
        assert cancel_resp.status_code == 202

        list_resp = c.get("/api/v3/inventories/inv-running/aisles")
        assert list_resp.status_code == 200
        list_data = list_resp.json()
        assert len(list_data) == 1
        assert list_data[0]["latest_job"] is not None
        assert list_data[0]["latest_job"]["status"] == "cancel_requested"

        status_resp = c.get(
            "/api/v3/inventories/inv-running/aisles/aisle-running/status",
        )
        assert status_resp.status_code == 200
        assert status_resp.json()["latest_job"] is not None
        assert status_resp.json()["latest_job"]["status"] == "cancel_requested"
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_inventory_repo, None)
        app.dependency_overrides.pop(get_aisle_repo, None)
        app.dependency_overrides.pop(get_job_repo, None)


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
    assert "created_at" in aisles2[0]["latest_job"], "aisle list latest_job must expose created_at (Phase 2 Block 2)"
    assert aisles2[0]["status"] == "queued"


def test_upload_aisle_assets_returns_201_and_assets() -> None:
    create_resp = client.post("/api/v3/inventories", json={"name": "For Upload"})
    assert create_resp.status_code == 201
    inv_id = create_resp.json()["id"]
    aisle_resp = client.post(
        f"/api/v3/inventories/{inv_id}/aisles",
        json={"code": "UP-01"},
    )
    assert aisle_resp.status_code == 201
    aisle_id = aisle_resp.json()["id"]

    response = client.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets",
        files=[("files", ("test.jpg", b"fake_jpeg_content", "image/jpeg"))],
    )
    assert response.status_code == 201
    data = response.json()
    assert "assets" in data
    assert len(data["assets"]) == 1
    assert data["assets"][0]["aisle_id"] == aisle_id
    assert data["assets"][0]["type"] == "photo"
    assert data["assets"][0]["original_filename"] == "test.jpg"


def test_upload_aisle_assets_aisle_not_found_returns_404() -> None:
    create_resp = client.post("/api/v3/inventories", json={"name": "For 404 Assets"})
    assert create_resp.status_code == 201
    inv_id = create_resp.json()["id"]

    response = client.post(
        f"/api/v3/inventories/{inv_id}/aisles/nonexistent-aisle-id/assets",
        files=[("files", ("x.jpg", b"x", "image/jpeg"))],
    )
    assert response.status_code == 404


def test_list_aisle_assets_returns_list() -> None:
    create_resp = client.post("/api/v3/inventories", json={"name": "For List Assets"})
    assert create_resp.status_code == 201
    inv_id = create_resp.json()["id"]
    aisle_resp = client.post(
        f"/api/v3/inventories/{inv_id}/aisles",
        json={"code": "LA-01"},
    )
    assert aisle_resp.status_code == 201
    aisle_id = aisle_resp.json()["id"]

    list_resp = client.get(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets")
    assert list_resp.status_code == 200
    assert list_resp.json() == []

    client.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets",
        files=[("files", ("a.jpg", b"a", "image/jpeg"))],
    )
    list_resp2 = client.get(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/assets")
    assert list_resp2.status_code == 200
    assets = list_resp2.json()
    assert len(assets) == 1
    assert assets[0]["original_filename"] == "a.jpg"


def test_list_aisle_assets_aisle_not_found_returns_404() -> None:
    create_resp = client.post("/api/v3/inventories", json={"name": "For List 404"})
    assert create_resp.status_code == 201
    inv_id = create_resp.json()["id"]

    response = client.get(
        f"/api/v3/inventories/{inv_id}/aisles/nonexistent-aisle/assets"
    )
    assert response.status_code == 404


# --- Épica 7: result consultation (positions list / detail) ---


def test_list_aisle_positions_returns_200_and_empty_list() -> None:
    """List positions returns 200 and positions array (empty when no results)."""
    create_resp = client.post("/api/v3/inventories", json={"name": "For Positions List"})
    assert create_resp.status_code == 201
    inv_id = create_resp.json()["id"]
    aisle_resp = client.post(
        f"/api/v3/inventories/{inv_id}/aisles",
        json={"code": "POS-01"},
    )
    assert aisle_resp.status_code == 201
    aisle_id = aisle_resp.json()["id"]

    response = client.get(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/positions"
    )
    assert response.status_code == 200
    data = response.json()
    assert "positions" in data
    assert isinstance(data["positions"], list)
    assert len(data["positions"]) == 0


def test_list_aisle_positions_inventory_not_found_returns_404() -> None:
    response = client.get(
        "/api/v3/inventories/nonexistent-inv-id/aisles/some-aisle-id/positions"
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_list_aisle_positions_aisle_not_found_returns_404() -> None:
    create_resp = client.post("/api/v3/inventories", json={"name": "For Positions 404"})
    assert create_resp.status_code == 201
    inv_id = create_resp.json()["id"]

    response = client.get(
        f"/api/v3/inventories/{inv_id}/aisles/nonexistent-aisle-id/positions"
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_position_detail_not_found_returns_404() -> None:
    create_resp = client.post("/api/v3/inventories", json={"name": "For Detail 404"})
    assert create_resp.status_code == 201
    inv_id = create_resp.json()["id"]
    aisle_resp = client.post(
        f"/api/v3/inventories/{inv_id}/aisles",
        json={"code": "D-01"},
    )
    assert aisle_resp.status_code == 201
    aisle_id = aisle_resp.json()["id"]

    response = client.get(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/positions/nonexistent-position-id"
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
