"""Jairo vs primary admin: real JWT flows without ``get_current_admin`` overrides."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from passlib.context import CryptContext

import src.config as config_module
from src.api.server import app
from src.auth.dependencies import get_current_admin
from src.config import reload_settings

_PWD_CONTEXT = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


@pytest.fixture(autouse=True)
def _jairo_integration_env(monkeypatch: pytest.MonkeyPatch):
    app.dependency_overrides.pop(get_current_admin, None)
    monkeypatch.setattr(config_module, "_load_dotenv_files", lambda for_reload=False: None)
    monkeypatch.setenv("SQLSERVER_ENABLED", "false")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", _PWD_CONTEXT.hash("primary-pw"))
    monkeypatch.setenv("AUTH_JAIRO_PASSWORD_HASH", _PWD_CONTEXT.hash("jairo-pw"))
    monkeypatch.setenv("AUTH_TOKEN_SECRET", "t" * 40)
    monkeypatch.setenv("AUTH_TOKEN_EXPIRES_MINUTES", "5")
    monkeypatch.setenv("AUTH_REFRESH_TOKEN_EXPIRES_MINUTES", "43200")
    reload_settings()
    yield
    app.dependency_overrides.pop(get_current_admin, None)


def _login_json(username: str, password: str) -> dict:
    client = TestClient(app)
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def test_jairo_auth_me_returns_expected_principal() -> None:
    token = _login_json("Jairo", "jairo-pw")["access_token"]
    client = TestClient(app)
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json() == {"id": "jairo", "username": "Jairo", "role": "administrator"}


def test_jairo_token_can_access_standard_v3_route() -> None:
    token = _login_json("Jairo", "jairo-pw")["access_token"]
    client = TestClient(app)
    r = client.get("/api/v3/inventories", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_jairo_token_forbidden_on_ai_config_inspection_route() -> None:
    token = _login_json("Jairo", "jairo-pw")["access_token"]
    client = TestClient(app)
    r = client.get("/api/v3/admin/ai-config", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
    assert r.json().get("error", {}).get("code") == "FORBIDDEN"


def test_primary_admin_token_succeeds_on_ai_config_inspection_route() -> None:
    token = _login_json("admin", "primary-pw")["access_token"]
    client = TestClient(app)
    r = client.get("/api/v3/admin/ai-config", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert "generated_at" in body
    assert isinstance(body.get("providers"), list)
