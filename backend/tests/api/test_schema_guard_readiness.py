from fastapi.testclient import TestClient

from src.api.schema_guard import schema_guard_state
from src.api.server import app


def test_ready_returns_503_when_schema_incompatible():
    schema_guard_state.checked = True
    schema_guard_state.compatible = False
    schema_guard_state.service = "inventory-api"
    schema_guard_state.required_version = "0003"
    schema_guard_state.current_version = "0002"
    schema_guard_state.reason = "database schema version 0002 is behind required version 0003"

    client = TestClient(app)
    response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["reason"] == "SCHEMA_INCOMPATIBLE"
    assert body["required_schema_version"] == "0003"
    assert body["current_schema_version"] == "0002"


def test_health_includes_schema_guard_metadata():
    schema_guard_state.checked = True
    schema_guard_state.compatible = True
    schema_guard_state.service = "inventory-api"
    schema_guard_state.required_version = "0002"
    schema_guard_state.current_version = "0002"
    schema_guard_state.reason = None

    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body.get("deploy_git_sha") in (None, "")
    assert body["schema_guard_checked"] is True
    assert body["schema_compatible"] is True
    assert body["required_schema_version"] == "0002"
