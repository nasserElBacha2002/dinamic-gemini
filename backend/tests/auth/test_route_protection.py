"""v3.2.1 Phase 3: backend route protection tests.

Verifies that public routes remain public, protected v3 routes require auth,
and auth failures return the stable error contract.
"""

import os
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from passlib.context import CryptContext

from src.api.server import app
from src.auth.security import create_access_token
from src.config import reload_settings


_PWD_CONTEXT = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

_STABLE_UNAUTHORIZED = {"error": {"code": "UNAUTHORIZED", "message": "Authentication required."}}


@pytest.fixture(autouse=True)
def _auth_env(monkeypatch: pytest.MonkeyPatch):
    """Ensure auth env vars are set for route protection tests."""
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", _PWD_CONTEXT.hash("correct-password"))
    monkeypatch.setenv("AUTH_TOKEN_SECRET", "t" * 40)
    monkeypatch.setenv("AUTH_TOKEN_EXPIRES_MINUTES", "5")
    reload_settings()
    yield


# --- Public routes ---


def test_health_remains_public():
    """Health endpoint must remain public (no auth required)."""
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_auth_login_remains_public():
    """POST /auth/login must remain public."""
    client = TestClient(app)
    r = client.post("/auth/login", json={"username": "admin", "password": "correct-password"})
    assert r.status_code == 200
    assert "access_token" in r.json()


# --- Protected v3 routes: missing / invalid / expired token ---


def test_v3_list_inventories_missing_token_unauthorized():
    """GET /api/v3/inventories without token returns 401 and stable envelope."""
    client = TestClient(app)
    r = client.get("/api/v3/inventories")
    assert r.status_code == 401
    assert r.json() == _STABLE_UNAUTHORIZED


def test_v3_list_inventories_invalid_token_unauthorized():
    """GET /api/v3/inventories with invalid token returns 401 and stable envelope."""
    client = TestClient(app)
    r = client.get(
        "/api/v3/inventories",
        headers={"Authorization": "Bearer not-a-valid-jwt"},
    )
    assert r.status_code == 401
    assert r.json() == _STABLE_UNAUTHORIZED


def test_v3_list_inventories_expired_token_unauthorized():
    """GET /api/v3/inventories with expired token returns 401 and stable envelope."""
    client = TestClient(app)
    token = create_access_token(
        "admin",
        username="admin",
        role="administrator",
        secret=os.environ["AUTH_TOKEN_SECRET"],
        expires_minutes=1,
        now=datetime(2000, 1, 1, tzinfo=timezone.utc),
    )
    r = client.get("/api/v3/inventories", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert r.json() == _STABLE_UNAUTHORIZED


def test_v3_post_inventories_missing_token_unauthorized():
    """POST /api/v3/inventories without token returns 401 and stable envelope."""
    client = TestClient(app)
    r = client.post("/api/v3/inventories", json={"name": "Test"})
    assert r.status_code == 401
    assert r.json() == _STABLE_UNAUTHORIZED


def test_v3_list_inventories_valid_token_reaches_handler():
    """With valid token, request passes auth and reaches business handler."""
    client = TestClient(app)
    login_r = client.post("/auth/login", json={"username": "admin", "password": "correct-password"})
    assert login_r.status_code == 200
    token = login_r.json()["access_token"]
    r = client.get("/api/v3/inventories", headers={"Authorization": f"Bearer {token}"})
    # Auth passed; handler returns 200 and list (may be empty)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)


def test_v3_protected_route_contract_no_detail():
    """Protected route auth failure must not return FastAPI default detail envelope."""
    client = TestClient(app)
    r = client.get("/api/v3/inventories")
    assert r.status_code == 401
    body = r.json()
    assert "error" in body
    assert body["error"]["code"] == "UNAUTHORIZED"
    # Must not be generic {"detail": "..."}
    assert "detail" not in body or body.get("detail") is None
