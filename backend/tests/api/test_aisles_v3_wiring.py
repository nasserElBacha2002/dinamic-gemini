"""API wiring tests: v3 aisle endpoints and inventory get by id."""

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import src.config as config_mod
from src.api.server import app
from src.api.dependencies import (
    get_artifact_storage,
    get_aisle_repo,
    get_evidence_repo,
    get_inventory_repo,
    get_job_repo,
    get_aisle_job_launch_service,
    get_job_stale_reconciler,
    get_position_repo,
    get_product_record_repo,
    get_review_action_repo,
)
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.domain.positions.entities import Position, PositionStatus
from src.domain.products.entities import ProductRecord
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_evidence_repository import MemoryEvidenceRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_product_record_repository import MemoryProductRecordRepository
from src.infrastructure.repositories.memory_review_action_repository import MemoryReviewActionRepository

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
    items = data["items"]
    assert isinstance(items, list)
    codes = [a["code"] for a in items]
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


def test_get_processing_provider_options_returns_registered_keys() -> None:
    app.dependency_overrides[get_current_admin] = _fake_admin
    try:
        response = client.get("/api/v3/inventories/processing-provider-options")
        assert response.status_code == 200
        data = response.json()
        assert "default_provider_key" in data
        assert "default_prompt_key" in data
        assert len(data.get("prompt_profiles", [])) >= 2
        keys = {p["key"] for p in data["providers"]}
        assert keys == {"fake", "gemini", "openai"}
        for p in data["providers"]:
            assert p["execution_mode"] in ("native", "transitional_bridge")
            assert "models" in p and isinstance(p["models"], list) and len(p["models"]) >= 1
            assert p.get("default_model")
        gemini = next(x for x in data["providers"] if x["key"] == "gemini")
        assert any(m["id"] == "gemini-2.0-flash-exp" for m in gemini["models"])
    finally:
        app.dependency_overrides.pop(get_current_admin, None)


def test_get_processing_provider_options_reflects_env_processing_model_lists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PROCESSING_*_MODELS must drive GET processing-provider-options (not only pydantic defaults)."""
    monkeypatch.setenv("PROCESSING_GEMINI_MODELS", "gemini-alpha,gemini-beta")
    monkeypatch.setenv("PROCESSING_OPENAI_MODELS", "gpt-alpha,gpt-beta")
    config_mod._settings = None
    app.dependency_overrides[get_current_admin] = _fake_admin
    try:
        response = client.get("/api/v3/inventories/processing-provider-options")
        assert response.status_code == 200
        data = response.json()
        gemini = next(p for p in data["providers"] if p["key"] == "gemini")
        openai_p = next(p for p in data["providers"] if p["key"] == "openai")
        assert [m["id"] for m in gemini["models"]] == ["gemini-alpha", "gemini-beta"]
        assert [m["id"] for m in openai_p["models"]] == ["gpt-alpha", "gpt-beta"]
        assert gemini["default_model"] == "gemini-alpha"
        assert openai_p["default_model"] == "gpt-alpha"
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        monkeypatch.delenv("PROCESSING_GEMINI_MODELS", raising=False)
        monkeypatch.delenv("PROCESSING_OPENAI_MODELS", raising=False)
        config_mod._settings = None


def test_post_process_with_explicit_fake_provider_persisted_on_status() -> None:
    app.dependency_overrides[get_current_admin] = _fake_admin
    try:
        create_resp = client.post("/api/v3/inventories", json={"name": "For Prov Fake"})
        assert create_resp.status_code == 201
        inv_id = create_resp.json()["id"]
        aisle_resp = client.post(
            f"/api/v3/inventories/{inv_id}/aisles",
            json={"code": "PF-01"},
        )
        assert aisle_resp.status_code == 201
        aisle_id = aisle_resp.json()["id"]

        proc = client.post(
            f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/process",
            json={"provider_name": "fake"},
        )
        assert proc.status_code == 202
        status = client.get(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/status")
        assert status.status_code == 200
        lj = status.json()["latest_job"]
        assert lj is not None
        assert lj.get("provider_name") == "fake"
        assert lj.get("model_name") == "fixture"
    finally:
        app.dependency_overrides.pop(get_current_admin, None)


def test_post_process_invalid_model_for_provider_returns_422() -> None:
    app.dependency_overrides[get_current_admin] = _fake_admin
    try:
        create_resp = client.post("/api/v3/inventories", json={"name": "For Bad Model"})
        assert create_resp.status_code == 201
        inv_id = create_resp.json()["id"]
        aisle_resp = client.post(
            f"/api/v3/inventories/{inv_id}/aisles",
            json={"code": "BM-01"},
        )
        assert aisle_resp.status_code == 201
        aisle_id = aisle_resp.json()["id"]
        response = client.post(
            f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/process",
            json={"provider_name": "fake", "model_name": "not-a-valid-model"},
        )
        assert response.status_code == 422
        assert "model" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_current_admin, None)


def test_post_process_unknown_provider_returns_422() -> None:
    app.dependency_overrides[get_current_admin] = _fake_admin
    try:
        create_resp = client.post("/api/v3/inventories", json={"name": "For Prov 422"})
        assert create_resp.status_code == 201
        inv_id = create_resp.json()["id"]
        aisle_resp = client.post(
            f"/api/v3/inventories/{inv_id}/aisles",
            json={"code": "PX-01"},
        )
        assert aisle_resp.status_code == 201
        aisle_id = aisle_resp.json()["id"]

        response = client.post(
            f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/process",
            json={"provider_name": "not-a-real-provider"},
        )
        assert response.status_code == 422
        assert "unknown" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_current_admin, None)


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


def test_status_and_list_expose_reference_usage_summary_from_job_result_json() -> None:
    now = datetime.now(timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository()

    inv_repo.save(Inventory("inv-reference-usage", "Reference Usage", InventoryStatus.DRAFT, now, now))
    aisle_repo.save(Aisle("aisle-reference-usage", "inv-reference-usage", "RU-01", AisleStatus.PROCESSED, now, now))
    job_repo.save(
        Job(
            id="job-reference-usage",
            target_type="aisle",
            target_id="aisle-reference-usage",
            job_type="process_aisle",
            status=JobStatus.SUCCEEDED,
            payload_json={"aisle_id": "aisle-reference-usage"},
            result_json={
                "visual_reference_context": {
                    "resolved": True,
                    "resolved_count": 2,
                    "provider_consumed": True,
                    "provider_consumed_count": 2,
                    "reference_ids": ["ref-1", "ref-2"],
                    "resolution_error": None,
                }
            },
            created_at=now,
            updated_at=now,
        )
    )

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_inventory_repo] = lambda: inv_repo
    app.dependency_overrides[get_aisle_repo] = lambda: aisle_repo
    app.dependency_overrides[get_job_repo] = lambda: job_repo
    try:
        c = TestClient(app)
        status_resp = c.get("/api/v3/inventories/inv-reference-usage/aisles/aisle-reference-usage/status")
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data["latest_job"]["reference_usage"] == {
            "resolved": True,
            "resolved_count": 2,
            "provider_consumed": True,
            "provider_consumed_count": 2,
            "reference_ids": ["ref-1", "ref-2"],
            "resolution_error": None,
        }

        list_resp = c.get("/api/v3/inventories/inv-reference-usage/aisles")
        assert list_resp.status_code == 200
        list_item = list_resp.json()["items"][0]
        assert list_item["latest_job"]["reference_usage"] == status_data["latest_job"]["reference_usage"]
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_inventory_repo, None)
        app.dependency_overrides.pop(get_aisle_repo, None)
        app.dependency_overrides.pop(get_job_repo, None)


def test_reference_usage_summary_tolerates_malformed_persisted_counts() -> None:
    now = datetime.now(timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository()

    inv_repo.save(Inventory("inv-malformed-usage", "Malformed Usage", InventoryStatus.DRAFT, now, now))
    aisle_repo.save(Aisle("aisle-malformed-usage", "inv-malformed-usage", "MU-01", AisleStatus.FAILED, now, now))
    job_repo.save(
        Job(
            id="job-malformed-usage",
            target_type="aisle",
            target_id="aisle-malformed-usage",
            job_type="process_aisle",
            status=JobStatus.FAILED,
            payload_json={"aisle_id": "aisle-malformed-usage"},
            result_json={
                "visual_reference_context": {
                    "resolved": True,
                    "resolved_count": "bad-value",
                    "provider_consumed": True,
                    "provider_consumed_count": None,
                    "reference_ids": [" ref-1 ", "", None, "ref-1", 3],
                    "resolution_error": "resolution warning",
                }
            },
            created_at=now,
            updated_at=now,
        )
    )

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_inventory_repo] = lambda: inv_repo
    app.dependency_overrides[get_aisle_repo] = lambda: aisle_repo
    app.dependency_overrides[get_job_repo] = lambda: job_repo
    try:
        c = TestClient(app)
        response = c.get("/api/v3/inventories/inv-malformed-usage/aisles/aisle-malformed-usage/status")
        assert response.status_code == 200
        usage = response.json()["latest_job"]["reference_usage"]
        assert usage == {
            "resolved": True,
            "resolved_count": 0,
            "provider_consumed": True,
            "provider_consumed_count": 0,
            "reference_ids": ["ref-1"],
            "resolution_error": "resolution warning",
        }
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_inventory_repo, None)
        app.dependency_overrides.pop(get_aisle_repo, None)
        app.dependency_overrides.pop(get_job_repo, None)


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
    aisles = list_resp.json()["items"]
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
    list_data = list_resp.json()["items"]
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
    cancel_data = cancel_resp.json()
    assert cancel_data["id"] == job_id
    assert cancel_data["status"] == "canceled"
    assert cancel_data["finished_at"] is not None
    assert cancel_data["cancel_requested_at"] is None

    list_resp = client.get(f"/api/v3/inventories/{inv_id}/aisles")
    assert list_resp.status_code == 200
    list_data = list_resp.json()["items"]
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
        cancel_data = cancel_resp.json()
        assert cancel_data["id"] == "job-running"
        assert cancel_data["status"] == "cancel_requested"
        assert cancel_data["cancel_requested_at"] is not None

        list_resp = c.get("/api/v3/inventories/inv-running/aisles")
        assert list_resp.status_code == 200
        list_data = list_resp.json()["items"]
        assert len(list_data) == 1
        assert list_data[0]["latest_job"] is not None
        assert list_data[0]["latest_job"]["status"] == "cancel_requested"

        status_resp = c.get(
            "/api/v3/inventories/inv-running/aisles/aisle-running/status",
        )
        assert status_resp.status_code == 200
        assert status_resp.json()["latest_job"] is not None
        assert status_resp.json()["latest_job"]["status"] == "cancel_requested"
        assert status_resp.json()["latest_job"]["cancel_requested_at"] is not None
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_inventory_repo, None)
        app.dependency_overrides.pop(get_aisle_repo, None)
        app.dependency_overrides.pop(get_job_repo, None)


def test_get_job_detail_returns_operational_metadata() -> None:
    now = datetime.now(timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository()

    inv_repo.save(Inventory("inv-job-detail", "Job Detail", InventoryStatus.DRAFT, now, now))
    aisle_repo.save(Aisle("aisle-job-detail", "inv-job-detail", "JD-01", AisleStatus.PROCESSING, now, now))
    job_repo.save(
        Job(
            id="job-job-detail",
            target_type="aisle",
            target_id="aisle-job-detail",
            job_type="process_aisle",
            status=JobStatus.CANCEL_REQUESTED,
            payload_json={"aisle_id": "aisle-job-detail"},
            created_at=now,
            updated_at=now,
            started_at=now,
            last_heartbeat_at=now,
            cancel_requested_at=now,
            current_stage="AnalysisStage",
            current_substep="provider_call",
            current_step_started_at=now,
            failure_code=None,
            failure_message="Job cancellation requested",
            execution_id="exec-123",
        )
    )

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_inventory_repo] = lambda: inv_repo
    app.dependency_overrides[get_aisle_repo] = lambda: aisle_repo
    app.dependency_overrides[get_job_repo] = lambda: job_repo
    try:
        c = TestClient(app)
        response = c.get("/api/v3/inventories/inv-job-detail/aisles/aisle-job-detail/jobs/job-job-detail")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancel_requested"
        assert data["started_at"] is not None
        assert data["last_heartbeat_at"] is not None
        assert data["cancel_requested_at"] is not None
        assert data["current_stage"] == "AnalysisStage"
        assert data["current_substep"] == "provider_call"
        assert data["execution_id"] == "exec-123"
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_inventory_repo, None)
        app.dependency_overrides.pop(get_aisle_repo, None)
        app.dependency_overrides.pop(get_job_repo, None)


def test_get_job_detail_applies_same_stale_reconciliation_as_status() -> None:
    now = datetime.now(timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository()

    inv_repo.save(Inventory("inv-job-stale", "Job Stale", InventoryStatus.DRAFT, now, now))
    aisle_repo.save(Aisle("aisle-job-stale", "inv-job-stale", "JS-01", AisleStatus.PROCESSING, now, now))
    job_repo.save(
        Job(
            id="job-job-stale",
            target_type="aisle",
            target_id="aisle-job-stale",
            job_type="process_aisle",
            status=JobStatus.CANCEL_REQUESTED,
            payload_json={"aisle_id": "aisle-job-stale"},
            created_at=now,
            updated_at=now,
            started_at=now,
            last_heartbeat_at=now,
            cancel_requested_at=now,
            current_stage="AnalysisStage",
            current_substep="provider_call",
        )
    )

    class StubStaleReconciler:
        def reconcile(self, job):  # type: ignore[no-untyped-def]
            if job is None:
                return None
            job.status = JobStatus.FAILED
            job.failure_code = "STALE_JOB"
            job.failure_message = "Job heartbeat expired before completion"
            job.error_message = "Job heartbeat expired before completion"
            return job

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_inventory_repo] = lambda: inv_repo
    app.dependency_overrides[get_aisle_repo] = lambda: aisle_repo
    app.dependency_overrides[get_job_repo] = lambda: job_repo
    app.dependency_overrides[get_job_stale_reconciler] = lambda: StubStaleReconciler()
    try:
        c = TestClient(app)
        job_resp = c.get("/api/v3/inventories/inv-job-stale/aisles/aisle-job-stale/jobs/job-job-stale")
        status_resp = c.get("/api/v3/inventories/inv-job-stale/aisles/aisle-job-stale/status")
        assert job_resp.status_code == 200
        assert status_resp.status_code == 200
        assert job_resp.json()["status"] == "failed"
        assert job_resp.json()["failure_code"] == "STALE_JOB"
        assert status_resp.json()["latest_job"]["status"] == "failed"
        assert status_resp.json()["latest_job"]["failure_code"] == "STALE_JOB"
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_inventory_repo, None)
        app.dependency_overrides.pop(get_aisle_repo, None)
        app.dependency_overrides.pop(get_job_repo, None)
        app.dependency_overrides.pop(get_job_stale_reconciler, None)


def test_retry_endpoint_returns_202_and_new_job_summary_with_lineage() -> None:
    now = datetime.now(timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository()

    class StubLaunchService:
        def __init__(self) -> None:
            self.launched: list[str] = []

        def create_and_launch_attempt(  # type: ignore[no-untyped-def]
            self,
            *,
            aisle,
            payload,
            attempt_count,
            retry_of_job_id=None,
            log_prefix="job.start_requested",
            provider_name="gemini",
            model_name=None,
            prompt_key="global_v21",
        ):
            job = Job(
                id="job-retry-created",
                target_type="aisle",
                target_id=aisle.id,
                job_type="process_aisle",
                status=JobStatus.STARTING,
                payload_json=dict(payload),
                created_at=now,
                updated_at=now,
                attempt_count=attempt_count,
                retry_of_job_id=retry_of_job_id,
                execution_id="exec-job-retry-created",
                provider_name=provider_name,
                model_name=model_name,
                prompt_key=prompt_key,
            )
            self.launched.append(job.id)
            job_repo.save(job)
            return job

    launch_service = StubLaunchService()

    inv_repo.save(Inventory("inv-retry", "Retry", InventoryStatus.DRAFT, now, now))
    aisle_repo.save(Aisle("aisle-retry", "inv-retry", "RT-01", AisleStatus.FAILED, now, now))
    job_repo.save(
        Job(
            id="job-failed",
            target_type="aisle",
            target_id="aisle-retry",
            job_type="process_aisle",
            status=JobStatus.FAILED,
            payload_json={"aisle_id": "aisle-retry"},
            created_at=now,
            updated_at=now,
            attempt_count=1,
            provider_name="fake",
            model_name="fixture",
            prompt_key="global_v21",
        )
    )

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_inventory_repo] = lambda: inv_repo
    app.dependency_overrides[get_aisle_repo] = lambda: aisle_repo
    app.dependency_overrides[get_job_repo] = lambda: job_repo
    app.dependency_overrides[get_aisle_job_launch_service] = lambda: launch_service
    try:
        c = TestClient(app)
        response = c.post("/api/v3/inventories/inv-retry/aisles/aisle-retry/jobs/job-failed/retry")
        assert response.status_code == 202
        data = response.json()
        assert data["id"] == "job-retry-created"
        assert data["status"] == "starting"
        assert data["attempt_count"] == 2
        assert data["retry_of_job_id"] == "job-failed"
        assert data["execution_id"] == "exec-job-retry-created"
        assert data.get("provider_name") == "fake"
        assert data.get("model_name") == "fixture"
        assert data.get("prompt_key") == "global_v21"
        assert launch_service.launched == [data["id"]]
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_inventory_repo, None)
        app.dependency_overrides.pop(get_aisle_repo, None)
        app.dependency_overrides.pop(get_job_repo, None)
        app.dependency_overrides.pop(get_aisle_job_launch_service, None)


def test_retry_endpoint_returns_409_for_non_retryable_status() -> None:
    now = datetime.now(timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository()

    inv_repo.save(Inventory("inv-retry-409", "Retry 409", InventoryStatus.DRAFT, now, now))
    aisle_repo.save(Aisle("aisle-retry-409", "inv-retry-409", "RT-02", AisleStatus.PROCESSING, now, now))
    job_repo.save(
        Job(
            id="job-running",
            target_type="aisle",
            target_id="aisle-retry-409",
            job_type="process_aisle",
            status=JobStatus.RUNNING,
            payload_json={"aisle_id": "aisle-retry-409"},
            created_at=now,
            updated_at=now,
        )
    )

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_inventory_repo] = lambda: inv_repo
    app.dependency_overrides[get_aisle_repo] = lambda: aisle_repo
    app.dependency_overrides[get_job_repo] = lambda: job_repo
    try:
        c = TestClient(app)
        response = c.post("/api/v3/inventories/inv-retry-409/aisles/aisle-retry-409/jobs/job-running/retry")
        assert response.status_code == 409
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_inventory_repo, None)
        app.dependency_overrides.pop(get_aisle_repo, None)
        app.dependency_overrides.pop(get_job_repo, None)


def test_retry_endpoint_returns_409_for_older_terminal_attempt_when_newer_retry_exists() -> None:
    now = datetime.now(timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository()

    inv_repo.save(Inventory("inv-retry-old", "Retry Old", InventoryStatus.DRAFT, now, now))
    aisle_repo.save(Aisle("aisle-retry-old", "inv-retry-old", "RT-OLD", AisleStatus.FAILED, now, now))
    job_repo.save(
        Job(
            id="job-old",
            target_type="aisle",
            target_id="aisle-retry-old",
            job_type="process_aisle",
            status=JobStatus.FAILED,
            payload_json={"aisle_id": "aisle-retry-old"},
            created_at=now,
            updated_at=now,
            attempt_count=1,
        )
    )
    later = datetime.now(timezone.utc)
    job_repo.save(
        Job(
            id="job-newer",
            target_type="aisle",
            target_id="aisle-retry-old",
            job_type="process_aisle",
            status=JobStatus.CANCELED,
            payload_json={"aisle_id": "aisle-retry-old"},
            created_at=later,
            updated_at=later,
            attempt_count=2,
            retry_of_job_id="job-old",
        )
    )

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_inventory_repo] = lambda: inv_repo
    app.dependency_overrides[get_aisle_repo] = lambda: aisle_repo
    app.dependency_overrides[get_job_repo] = lambda: job_repo
    try:
        c = TestClient(app)
        response = c.post("/api/v3/inventories/inv-retry-old/aisles/aisle-retry-old/jobs/job-old/retry")
        assert response.status_code == 409
        assert "latest retryable terminal attempt is job-newer" in response.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_inventory_repo, None)
        app.dependency_overrides.pop(get_aisle_repo, None)
        app.dependency_overrides.pop(get_job_repo, None)


def test_status_and_job_detail_expose_retry_lineage() -> None:
    now = datetime.now(timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository()

    inv_repo.save(Inventory("inv-retry-lineage", "Retry Lineage", InventoryStatus.DRAFT, now, now))
    aisle_repo.save(Aisle("aisle-retry-lineage", "inv-retry-lineage", "RT-03", AisleStatus.QUEUED, now, now))
    job_repo.save(
        Job(
            id="job-retry-lineage",
            target_type="aisle",
            target_id="aisle-retry-lineage",
            job_type="process_aisle",
            status=JobStatus.STARTING,
            payload_json={"aisle_id": "aisle-retry-lineage"},
            created_at=now,
            updated_at=now,
            attempt_count=3,
            retry_of_job_id="job-retry-parent",
        )
    )

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_inventory_repo] = lambda: inv_repo
    app.dependency_overrides[get_aisle_repo] = lambda: aisle_repo
    app.dependency_overrides[get_job_repo] = lambda: job_repo
    try:
        c = TestClient(app)
        status_resp = c.get("/api/v3/inventories/inv-retry-lineage/aisles/aisle-retry-lineage/status")
        detail_resp = c.get("/api/v3/inventories/inv-retry-lineage/aisles/aisle-retry-lineage/jobs/job-retry-lineage")
        assert status_resp.status_code == 200
        assert detail_resp.status_code == 200
        assert status_resp.json()["latest_job"]["retry_of_job_id"] == "job-retry-parent"
        assert status_resp.json()["latest_job"]["attempt_count"] == 3
        assert detail_resp.json()["retry_of_job_id"] == "job-retry-parent"
        assert detail_resp.json()["attempt_count"] == 3
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_inventory_repo, None)
        app.dependency_overrides.pop(get_aisle_repo, None)
        app.dependency_overrides.pop(get_job_repo, None)


def test_post_process_when_latest_job_running_returns_409() -> None:
    """Phase 3 Case 4: Active job (RUNNING) blocks duplicate process start; API returns 409."""
    now = datetime.now(timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository()

    inv = Inventory("inv-block", "For Block", InventoryStatus.DRAFT, now, now)
    inv_repo.save(inv)
    aisle = Aisle("aisle-block", "inv-block", "B-01", AisleStatus.CREATED, now, now)
    aisle_repo.save(aisle)
    job = Job(
        id="job-running-block",
        target_type="aisle",
        target_id="aisle-block",
        job_type="process_aisle",
        status=JobStatus.RUNNING,
        payload_json={"aisle_id": "aisle-block"},
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
        resp = c.post(
            "/api/v3/inventories/inv-block/aisles/aisle-block/process",
        )
        assert resp.status_code == 409
        assert "active" in resp.json().get("detail", "").lower()
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_inventory_repo, None)
        app.dependency_overrides.pop(get_aisle_repo, None)
        app.dependency_overrides.pop(get_job_repo, None)


def test_post_process_after_terminal_job_creates_new_job() -> None:
    """Phase 3 Case 5: After terminal state (e.g. CANCELED), POST process creates a new job; list/status show new job."""
    create_resp = client.post("/api/v3/inventories", json={"name": "For Re-process"})
    assert create_resp.status_code == 201
    inv_id = create_resp.json()["id"]
    aisle_resp = client.post(
        f"/api/v3/inventories/{inv_id}/aisles",
        json={"code": "RP-01"},
    )
    assert aisle_resp.status_code == 201
    aisle_id = aisle_resp.json()["id"]
    process1 = client.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/process",
    )
    assert process1.status_code == 202
    job_id_1 = process1.json()["job_id"]
    cancel_resp = client.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/jobs/{job_id_1}/cancel",
    )
    assert cancel_resp.status_code == 202

    process2 = client.post(
        f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/process",
    )
    assert process2.status_code == 202
    job_id_2 = process2.json()["job_id"]
    assert job_id_2 != job_id_1

    list_resp = client.get(f"/api/v3/inventories/{inv_id}/aisles")
    assert list_resp.status_code == 200
    assert list_resp.json()["items"][0]["latest_job"]["id"] == job_id_2
    assert list_resp.json()["items"][0]["latest_job"]["status"] == "queued"

    status_resp = client.get(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["latest_job"]["id"] == job_id_2
    assert status_resp.json()["latest_job"]["status"] == "queued"


def test_execution_log_and_lifecycle_when_artifacts_missing() -> None:
    """Phase 7 Block 2 Case 1: Missing run directory — 200, events: [], lifecycle remains DB-authoritative."""
    now = datetime.now(timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository()

    inv = Inventory("inv-art", "For Artifacts", InventoryStatus.DRAFT, now, now)
    inv_repo.save(inv)
    aisle = Aisle("aisle-art", "inv-art", "ART-01", AisleStatus.CREATED, now, now)
    aisle_repo.save(aisle)
    job = Job(
        id="job-art-1",
        target_type="aisle",
        target_id="aisle-art",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={"aisle_id": "aisle-art"},
        created_at=now,
        updated_at=now,
    )
    job_repo.save(job)

    from src.infrastructure.storage.v3_artifact_storage_adapter import V3ArtifactStorageAdapter

    _art_base = Path(tempfile.mkdtemp(prefix="exec_log_art_"))
    store = V3ArtifactStorageAdapter(_art_base)

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_inventory_repo] = lambda: inv_repo
    app.dependency_overrides[get_aisle_repo] = lambda: aisle_repo
    app.dependency_overrides[get_job_repo] = lambda: job_repo
    app.dependency_overrides[get_artifact_storage] = lambda: store
    try:
        c = TestClient(app)
        status_resp = c.get(
            "/api/v3/inventories/inv-art/aisles/aisle-art/status",
        )
        assert status_resp.status_code == 200
        assert status_resp.json()["latest_job"] is not None
        assert status_resp.json()["latest_job"]["status"] == "succeeded"
        assert status_resp.json()["latest_job"]["id"] == "job-art-1"

        log_resp = c.get(
            "/api/v3/inventories/inv-art/aisles/aisle-art/jobs/job-art-1/execution-log",
        )
        assert log_resp.status_code == 200
        data = log_resp.json()
        assert "events" in data
        assert data["events"] == [], "missing run dir must yield events: [] (degraded diagnostic)"
        assert isinstance(data["events"], list)

        # Lifecycle unchanged and DB-authoritative after reading log
        status_resp2 = c.get("/api/v3/inventories/inv-art/aisles/aisle-art/status")
        assert status_resp2.status_code == 200
        assert status_resp2.json()["latest_job"]["status"] == "succeeded"
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_inventory_repo, None)
        app.dependency_overrides.pop(get_aisle_repo, None)
        app.dependency_overrides.pop(get_job_repo, None)
        app.dependency_overrides.pop(get_artifact_storage, None)
        import shutil

        shutil.rmtree(_art_base, ignore_errors=True)


def test_execution_log_returns_200_empty_events_when_run_dir_exists_but_file_missing() -> None:
    """Phase 7 Block 2 Case 2: Run dir exists, execution_log.jsonl missing — 200, events: []."""
    now = datetime.now(timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository()

    inv = Inventory("inv-el", "Exec Log", InventoryStatus.DRAFT, now, now)
    inv_repo.save(inv)
    aisle = Aisle("aisle-el", "inv-el", "EL-01", AisleStatus.CREATED, now, now)
    aisle_repo.save(aisle)
    job = Job(
        id="job-el-1",
        target_type="aisle",
        target_id="aisle-el",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={"aisle_id": "aisle-el"},
        created_at=now,
        updated_at=now,
    )
    job_repo.save(job)

    base = Path(tempfile.mkdtemp(prefix="phase7_exec_log_"))
    run_dir = base / "job-el-1" / "run"
    run_dir.mkdir(parents=True)
    try:
        from src.infrastructure.storage.v3_artifact_storage_adapter import V3ArtifactStorageAdapter

        fake_settings = type(
            "Settings",
            (),
            {
                "output_dir": str(base),
                "artifact_storage_legacy_local_read_enabled": True,
                "artifact_s3_signed_url_ttl_sec": 900,
                "artifact_store_max_in_memory_get_bytes": 8 * 1024 * 1024,
                "artifact_store_max_json_load_bytes": 32 * 1024 * 1024,
            },
        )()
        mock_load = patch(
            "src.api.services.v3_stored_artifact_access.load_settings",
            return_value=fake_settings,
        )
        store = V3ArtifactStorageAdapter(base.parent / "artifact_store_unused")
        app.dependency_overrides[get_current_admin] = _fake_admin
        app.dependency_overrides[get_inventory_repo] = lambda: inv_repo
        app.dependency_overrides[get_aisle_repo] = lambda: aisle_repo
        app.dependency_overrides[get_job_repo] = lambda: job_repo
        app.dependency_overrides[get_artifact_storage] = lambda: store
        try:
            mock_load.start()
            c = TestClient(app)
            log_resp = c.get(
                "/api/v3/inventories/inv-el/aisles/aisle-el/jobs/job-el-1/execution-log",
            )
            assert log_resp.status_code == 200
            assert log_resp.json()["events"] == []
        finally:
            mock_load.stop()
            app.dependency_overrides.pop(get_current_admin, None)
            app.dependency_overrides.pop(get_inventory_repo, None)
            app.dependency_overrides.pop(get_aisle_repo, None)
            app.dependency_overrides.pop(get_job_repo, None)
            app.dependency_overrides.pop(get_artifact_storage, None)
    finally:
        try:
            import shutil
            shutil.rmtree(base, ignore_errors=True)
        except Exception:
            pass


def test_execution_log_returns_events_for_canceled_job() -> None:
    now = datetime.now(timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository()

    inv = Inventory("inv-cancel-log", "Canceled Log", InventoryStatus.DRAFT, now, now)
    inv_repo.save(inv)
    aisle = Aisle("aisle-cancel-log", "inv-cancel-log", "CL-01", AisleStatus.FAILED, now, now)
    aisle_repo.save(aisle)
    job = Job(
        id="job-cancel-log",
        target_type="aisle",
        target_id="aisle-cancel-log",
        job_type="process_aisle",
        status=JobStatus.CANCELED,
        payload_json={"aisle_id": "aisle-cancel-log"},
        created_at=now,
        updated_at=now,
        finished_at=now,
        error_message="Job canceled by operator request",
    )
    job_repo.save(job)

    base = Path(tempfile.mkdtemp(prefix="phase8_cancel_exec_log_"))
    run_dir = base / "job-cancel-log" / "run"
    run_dir.mkdir(parents=True)
    (run_dir / "execution_log.jsonl").write_text(
        '\n'.join(
            [
                '{"ts":"2025-01-01T00:00:00+00:00","stage":"AnalysisStage","level":"info","message":"job.cancel_requested","payload":{"event":"job.cancel_requested"}}',
                '{"ts":"2025-01-01T00:00:01+00:00","stage":"Pipeline","level":"info","message":"job.canceled","payload":{"event":"job.canceled"}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    try:
        from src.infrastructure.storage.v3_artifact_storage_adapter import V3ArtifactStorageAdapter

        fake_settings = type(
            "Settings",
            (),
            {"output_dir": str(base), "artifact_storage_legacy_local_read_enabled": True},
        )()
        store = V3ArtifactStorageAdapter(base / "artifact-root")
        app.dependency_overrides[get_current_admin] = _fake_admin
        app.dependency_overrides[get_inventory_repo] = lambda: inv_repo
        app.dependency_overrides[get_aisle_repo] = lambda: aisle_repo
        app.dependency_overrides[get_job_repo] = lambda: job_repo
        app.dependency_overrides[get_artifact_storage] = lambda: store
        with patch("src.api.services.v3_stored_artifact_access.load_settings", return_value=fake_settings):
            c = TestClient(app)
            response = c.get(
                "/api/v3/inventories/inv-cancel-log/aisles/aisle-cancel-log/jobs/job-cancel-log/execution-log"
            )
        assert response.status_code == 200
        messages = [event["message"] for event in response.json()["events"]]
        assert "job.cancel_requested" in messages
        assert "job.canceled" in messages
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_inventory_repo, None)
        app.dependency_overrides.pop(get_aisle_repo, None)
        app.dependency_overrides.pop(get_job_repo, None)
        app.dependency_overrides.pop(get_artifact_storage, None)
        import shutil

        shutil.rmtree(base, ignore_errors=True)


def test_execution_log_job_not_found_returns_404() -> None:
    """Phase 7 Block 2 Case 4: Ownership — job not found returns 404."""
    now = datetime.now(timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository()
    inv = Inventory("inv-el404", "EL 404", InventoryStatus.DRAFT, now, now)
    inv_repo.save(inv)
    aisle = Aisle("aisle-el404", "inv-el404", "EL-404", AisleStatus.CREATED, now, now)
    aisle_repo.save(aisle)
    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_inventory_repo] = lambda: inv_repo
    app.dependency_overrides[get_aisle_repo] = lambda: aisle_repo
    app.dependency_overrides[get_job_repo] = lambda: job_repo
    try:
        c = TestClient(app)
        log_resp = c.get(
            "/api/v3/inventories/inv-el404/aisles/aisle-el404/jobs/nonexistent-job-id/execution-log",
        )
        assert log_resp.status_code == 404
        assert "not found" in log_resp.json().get("detail", "").lower()
    finally:
        app.dependency_overrides.clear()


def test_execution_log_job_wrong_aisle_returns_404() -> None:
    """Phase 7 Block 2 Case 4: Job belongs to different aisle — 404."""
    now = datetime.now(timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository()
    inv = Inventory("inv-ela", "EL A", InventoryStatus.DRAFT, now, now)
    inv_repo.save(inv)
    aisle = Aisle("aisle-ela", "inv-ela", "ELA", AisleStatus.CREATED, now, now)
    aisle_repo.save(aisle)
    job = Job(
        id="job-other-aisle",
        target_type="aisle",
        target_id="other-aisle-id",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={},
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
        log_resp = c.get(
            "/api/v3/inventories/inv-ela/aisles/aisle-ela/jobs/job-other-aisle/execution-log",
        )
        assert log_resp.status_code == 404
        assert "not found" in log_resp.json().get("detail", "").lower() or "not belong" in log_resp.json().get("detail", "").lower()
    finally:
        app.dependency_overrides.clear()


def test_execution_log_aisle_wrong_inventory_returns_404() -> None:
    """Phase 7 Block 2 Case 4: Aisle does not belong to inventory — 404."""
    now = datetime.now(timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository()
    inv = Inventory("inv-eli", "EL Inv", InventoryStatus.DRAFT, now, now)
    inv_repo.save(inv)
    aisle = Aisle("aisle-eli", "inv-eli", "ELI", AisleStatus.CREATED, now, now)
    aisle_repo.save(aisle)
    job = Job(
        id="job-eli",
        target_type="aisle",
        target_id="aisle-eli",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={},
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
        log_resp = c.get(
            "/api/v3/inventories/wrong-inventory-id/aisles/aisle-eli/jobs/job-eli/execution-log",
        )
        assert log_resp.status_code == 404
        assert "not found" in log_resp.json().get("detail", "").lower() or "not belong" in log_resp.json().get("detail", "").lower()
    finally:
        app.dependency_overrides.clear()


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
    aisles = list_resp.json()["items"]
    assert len(aisles) == 1
    assert aisles[0].get("latest_job") is None

    client.post(f"/api/v3/inventories/{inv_id}/aisles/{aisle_id}/process")
    list_resp2 = client.get(f"/api/v3/inventories/{inv_id}/aisles")
    assert list_resp2.status_code == 200
    aisles2 = list_resp2.json()["items"]
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


def test_positions_list_and_detail_degrade_only_enrichment_when_hybrid_report_missing() -> None:
    """Phase 7 Block 7.1: Missing hybrid_report.json does not corrupt DB-backed truth.

    When a position has entity_uid but no traceability/source-image fields in stored summary
    and no matching hybrid_report.json exists on disk:
    - GET list and GET detail return 200.
    - DB-backed fields (status, needs_review, qty, corrected_quantity, qtySource, review truth)
      remain coherent and authoritative.
    - Only optional enrichment fields (source_image_id, traceability_status,
      source_image_original_filename) degrade to null.
    - No non-null enriched values are fabricated.
    """
    now = datetime.now(timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    position_repo = MemoryPositionRepository()
    product_repo = MemoryProductRecordRepository()
    evidence_repo = MemoryEvidenceRepository()
    review_repo = MemoryReviewActionRepository()

    inv = Inventory("inv-p7", "Phase7 Artifacts", InventoryStatus.DRAFT, now, now)
    inv_repo.save(inv)
    aisle = Aisle("aisle-p7", "inv-p7", "P7-01", AisleStatus.CREATED, now, now)
    aisle_repo.save(aisle)
    # Position has entity_uid so enrichment is attempted; no source_image_id / traceability_status
    # / source_image_original_filename in stored summary so enrichment would fill them if report existed.
    position = Position(
        id="pos-p7",
        aisle_id="aisle-p7",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=True,
        primary_evidence_id=None,
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "entity_uid": "job-no-hr_ent1",
            "internal_code": "SKU-P7",
        },
    )
    position_repo.save(position)
    product = ProductRecord(
        id="prod-p7",
        position_id="pos-p7",
        sku="SKU-P7",
        description="Phase7 product",
        detected_quantity=3,
        corrected_quantity=None,
        confidence=0.95,
        created_at=now,
        updated_at=now,
        qty_source="detected",
        qty_inference_reason=None,
    )
    product_repo.save(product)

    # output_dir with no job-no-hr/run/hybrid_report.json so enrichment finds nothing
    empty_output = Path(tempfile.mkdtemp(prefix="phase7_empty_output_"))
    try:
        mock_settings = patch(
            "src.api.routes.v3.shared.load_settings",
            return_value=type("Settings", (), {"output_dir": empty_output})(),
        )
        app.dependency_overrides[get_current_admin] = _fake_admin
        app.dependency_overrides[get_inventory_repo] = lambda: inv_repo
        app.dependency_overrides[get_aisle_repo] = lambda: aisle_repo
        app.dependency_overrides[get_position_repo] = lambda: position_repo
        app.dependency_overrides[get_product_record_repo] = lambda: product_repo
        app.dependency_overrides[get_evidence_repo] = lambda: evidence_repo
        app.dependency_overrides[get_review_action_repo] = lambda: review_repo
        try:
            mock_settings.start()
            c = TestClient(app)
            list_resp = c.get("/api/v3/inventories/inv-p7/aisles/aisle-p7/positions")
            assert list_resp.status_code == 200, list_resp.text
            list_data = list_resp.json()
            assert "positions" in list_data
            assert len(list_data["positions"]) == 1
            list_pos = list_data["positions"][0]

            detail_resp = c.get(
                "/api/v3/inventories/inv-p7/aisles/aisle-p7/positions/pos-p7"
            )
            assert detail_resp.status_code == 200, detail_resp.text
            detail_data = detail_resp.json()
            assert "position" in detail_data
            detail_pos = detail_data["position"]

            for pos_payload in (list_pos, detail_pos):
                # DB-backed fields remain coherent and authoritative
                assert pos_payload["status"] == "detected"
                assert pos_payload["needs_review"] is True
                assert pos_payload["qty"] == 3
                assert pos_payload["qtySource"] == "detected"
                assert pos_payload.get("corrected_quantity") is None
                # Optional enrichment fields degrade to null (no fabrication)
                assert pos_payload.get("source_image_id") is None
                assert pos_payload.get("traceability_status") is None
                assert pos_payload.get("source_image_original_filename") is None
                # Semantic alignment: list and detail same for these fields
                assert pos_payload["id"] == "pos-p7"
                assert pos_payload.get("sku") == "SKU-P7"

            assert list_pos["status"] == detail_pos["status"]
            assert list_pos["qty"] == detail_pos["qty"]
            assert list_pos.get("source_image_id") == detail_pos.get("source_image_id")
        finally:
            mock_settings.stop()
            app.dependency_overrides.pop(get_current_admin, None)
            app.dependency_overrides.pop(get_inventory_repo, None)
            app.dependency_overrides.pop(get_aisle_repo, None)
            app.dependency_overrides.pop(get_position_repo, None)
            app.dependency_overrides.pop(get_product_record_repo, None)
            app.dependency_overrides.pop(get_evidence_repo, None)
            app.dependency_overrides.pop(get_review_action_repo, None)
    finally:
        try:
            empty_output.rmdir()
        except OSError:
            pass


def test_execution_log_from_durable_metadata_not_local_disk() -> None:
    """Phase 4: execution log is read from ArtifactStore when durable metadata exists."""
    import json
    import shutil

    from src.infrastructure.pipeline.worker_durable_artifact_publisher import (
        DURABLE_ARTIFACT_KIND_EXECUTION_LOG,
    )
    from src.infrastructure.storage.v3_artifact_storage_adapter import V3ArtifactStorageAdapter

    now = datetime.now(timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository()

    inv = Inventory("inv-p4", "Phase4", InventoryStatus.DRAFT, now, now)
    inv_repo.save(inv)
    aisle = Aisle("aisle-p4", "inv-p4", "P4", AisleStatus.CREATED, now, now)
    aisle_repo.save(aisle)

    job_id = "job-p4-durable"
    log_key = f"jobs/{job_id}/run/execution_log.jsonl"
    line = {"ts": "2026-01-01T00:00:00", "stage": "s", "level": "info", "message": "m"}
    payload = (json.dumps(line, ensure_ascii=False) + "\n").encode("utf-8")

    art_root = Path(tempfile.mkdtemp(prefix="p4_exec_"))
    store = V3ArtifactStorageAdapter(art_root)
    from io import BytesIO

    store.put_object(log_key, BytesIO(payload), "application/x-ndjson")

    job = Job(
        id=job_id,
        target_type="aisle",
        target_id="aisle-p4",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={"aisle_id": "aisle-p4"},
        created_at=now,
        updated_at=now,
        result_json={
            "durable_artifacts": {
                DURABLE_ARTIFACT_KIND_EXECUTION_LOG: {
                    "storage_provider": "local",
                    "storage_bucket": None,
                    "storage_key": log_key,
                    "content_type": "application/x-ndjson",
                    "file_size_bytes": len(payload),
                    "etag": None,
                }
            }
        },
    )
    job_repo.save(job)

    # output_dir has no job/run — proves durable path is used
    bogus_out = Path(tempfile.mkdtemp(prefix="p4_bogus_out_"))

    fake_settings = type(
        "Settings",
        (),
        {
            "output_dir": str(bogus_out),
            "artifact_storage_legacy_local_read_enabled": False,
            "artifact_s3_signed_url_ttl_sec": 900,
            "artifact_store_max_in_memory_get_bytes": 8 * 1024 * 1024,
            "artifact_store_max_json_load_bytes": 32 * 1024 * 1024,
        },
    )()
    mock_st = patch(
        "src.api.services.v3_stored_artifact_access.load_settings",
        return_value=fake_settings,
    )
    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_inventory_repo] = lambda: inv_repo
    app.dependency_overrides[get_aisle_repo] = lambda: aisle_repo
    app.dependency_overrides[get_job_repo] = lambda: job_repo
    app.dependency_overrides[get_artifact_storage] = lambda: store
    try:
        mock_st.start()
        c = TestClient(app)
        log_resp = c.get(
            f"/api/v3/inventories/inv-p4/aisles/aisle-p4/jobs/{job_id}/execution-log",
        )
        assert log_resp.status_code == 200, log_resp.text
        assert len(log_resp.json()["events"]) == 1
        assert log_resp.json()["events"][0]["message"] == "m"
    finally:
        mock_st.stop()
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_inventory_repo, None)
        app.dependency_overrides.pop(get_aisle_repo, None)
        app.dependency_overrides.pop(get_job_repo, None)
        app.dependency_overrides.pop(get_artifact_storage, None)
        shutil.rmtree(art_root, ignore_errors=True)
        shutil.rmtree(bogus_out, ignore_errors=True)


def test_execution_log_legacy_disabled_without_durable_returns_404() -> None:
    import shutil

    now = datetime.now(timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository()

    inv = Inventory("inv-p4b", "Phase4b", InventoryStatus.DRAFT, now, now)
    inv_repo.save(inv)
    aisle = Aisle("aisle-p4b", "inv-p4b", "P4b", AisleStatus.CREATED, now, now)
    aisle_repo.save(aisle)
    job = Job(
        id="job-p4b",
        target_type="aisle",
        target_id="aisle-p4b",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={"aisle_id": "aisle-p4b"},
        created_at=now,
        updated_at=now,
    )
    job_repo.save(job)

    bogus_out = Path(tempfile.mkdtemp(prefix="p4b_out_"))
    from src.infrastructure.storage.v3_artifact_storage_adapter import V3ArtifactStorageAdapter

    store = V3ArtifactStorageAdapter(Path(tempfile.mkdtemp(prefix="p4b_art_")))

    fake_settings = type(
        "Settings",
        (),
        {
            "output_dir": str(bogus_out),
            "artifact_storage_legacy_local_read_enabled": False,
            "artifact_s3_signed_url_ttl_sec": 900,
            "artifact_store_max_in_memory_get_bytes": 8 * 1024 * 1024,
            "artifact_store_max_json_load_bytes": 32 * 1024 * 1024,
        },
    )()
    mock_st = patch(
        "src.api.services.v3_stored_artifact_access.load_settings",
        return_value=fake_settings,
    )
    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_inventory_repo] = lambda: inv_repo
    app.dependency_overrides[get_aisle_repo] = lambda: aisle_repo
    app.dependency_overrides[get_job_repo] = lambda: job_repo
    app.dependency_overrides[get_artifact_storage] = lambda: store
    try:
        mock_st.start()
        c = TestClient(app)
        log_resp = c.get(
            "/api/v3/inventories/inv-p4b/aisles/aisle-p4b/jobs/job-p4b/execution-log",
        )
        assert log_resp.status_code == 404
        assert "not available" in log_resp.json().get("detail", "").lower()
    finally:
        mock_st.stop()
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_inventory_repo, None)
        app.dependency_overrides.pop(get_aisle_repo, None)
        app.dependency_overrides.pop(get_job_repo, None)
        app.dependency_overrides.pop(get_artifact_storage, None)
        shutil.rmtree(bogus_out, ignore_errors=True)


def test_hybrid_report_api_from_durable_metadata() -> None:
    import json
    import shutil
    from io import BytesIO

    from src.infrastructure.pipeline.worker_durable_artifact_publisher import (
        DURABLE_ARTIFACT_KIND_HYBRID_REPORT_JSON,
    )
    from src.infrastructure.storage.v3_artifact_storage_adapter import V3ArtifactStorageAdapter

    now = datetime.now(timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository()

    inv = Inventory("inv-p4c", "Phase4c", InventoryStatus.DRAFT, now, now)
    inv_repo.save(inv)
    aisle = Aisle("aisle-p4c", "inv-p4c", "P4c", AisleStatus.CREATED, now, now)
    aisle_repo.save(aisle)

    job_id = "job-p4c"
    rkey = f"jobs/{job_id}/run/hybrid_report.json"
    report_body = {"entities": [{"entity_uid": f"{job_id}_e1"}]}
    raw = json.dumps(report_body).encode("utf-8")

    art_root = Path(tempfile.mkdtemp(prefix="p4c_art_"))
    store = V3ArtifactStorageAdapter(art_root)
    store.put_object(rkey, BytesIO(raw), "application/json")

    job = Job(
        id=job_id,
        target_type="aisle",
        target_id="aisle-p4c",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={"aisle_id": "aisle-p4c"},
        created_at=now,
        updated_at=now,
        result_json={
            "durable_artifacts": {
                DURABLE_ARTIFACT_KIND_HYBRID_REPORT_JSON: {
                    "storage_provider": "local",
                    "storage_bucket": None,
                    "storage_key": rkey,
                    "content_type": "application/json",
                    "file_size_bytes": len(raw),
                    "etag": None,
                }
            }
        },
    )
    job_repo.save(job)

    bogus_out = Path(tempfile.mkdtemp(prefix="p4c_out_"))
    fake_settings = type(
        "Settings",
        (),
        {
            "output_dir": str(bogus_out),
            "artifact_storage_legacy_local_read_enabled": False,
            "artifact_s3_signed_url_ttl_sec": 900,
            "artifact_store_max_in_memory_get_bytes": 8 * 1024 * 1024,
            "artifact_store_max_json_load_bytes": 32 * 1024 * 1024,
        },
    )()
    mock_st = patch(
        "src.api.services.v3_stored_artifact_access.load_settings",
        return_value=fake_settings,
    )
    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_inventory_repo] = lambda: inv_repo
    app.dependency_overrides[get_aisle_repo] = lambda: aisle_repo
    app.dependency_overrides[get_job_repo] = lambda: job_repo
    app.dependency_overrides[get_artifact_storage] = lambda: store
    try:
        mock_st.start()
        c = TestClient(app)
        hr = c.get(
            f"/api/v3/inventories/inv-p4c/aisles/aisle-p4c/jobs/{job_id}/hybrid-report",
        )
        assert hr.status_code == 200, hr.text
        assert hr.json()["entities"][0]["entity_uid"] == f"{job_id}_e1"
    finally:
        mock_st.stop()
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_inventory_repo, None)
        app.dependency_overrides.pop(get_aisle_repo, None)
        app.dependency_overrides.pop(get_job_repo, None)
        app.dependency_overrides.pop(get_artifact_storage, None)
        shutil.rmtree(art_root, ignore_errors=True)
        shutil.rmtree(bogus_out, ignore_errors=True)
