import os
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from passlib.context import CryptContext

from src.api.server import app
from src.auth.security import create_access_token
from src.config import reload_settings


_PWD_CONTEXT = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


@pytest.fixture(autouse=True)
def _auth_env(monkeypatch: pytest.MonkeyPatch):
    """
    Ensure auth env vars are present for auth tests.
    """
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", _PWD_CONTEXT.hash("correct-password"))
    monkeypatch.setenv("AUTH_TOKEN_SECRET", "t" * 40)
    monkeypatch.setenv("AUTH_TOKEN_EXPIRES_MINUTES", "5")
    reload_settings()
    yield


def test_auth_login_success():
    client = TestClient(app)
    r = client.post("/auth/login", json={"username": "admin", "password": "correct-password"})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data.get("access_token"), str) and data["access_token"]
    assert data.get("token_type") == "bearer"
    assert isinstance(data.get("expires_in"), int) and data["expires_in"] > 0
    assert data["user"]["id"] == "admin"
    assert data["user"]["username"] == "admin"
    assert data["user"]["role"] == "administrator"


def test_auth_login_invalid_credentials():
    client = TestClient(app)
    r = client.post("/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401
    assert r.json() == {"error": {"code": "INVALID_CREDENTIALS", "message": "Invalid credentials."}}


def test_auth_me_success_with_valid_token():
    client = TestClient(app)
    login_r = client.post("/auth/login", json={"username": "admin", "password": "correct-password"})
    assert login_r.status_code == 200
    token = login_r.json()["access_token"]
    me_r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_r.status_code == 200
    assert me_r.json() == {"id": "admin", "username": "admin", "role": "administrator"}


def test_auth_me_missing_token_unauthorized():
    client = TestClient(app)
    r = client.get("/auth/me")
    assert r.status_code == 401
    assert r.json() == {"error": {"code": "UNAUTHORIZED", "message": "Authentication required."}}


def test_auth_me_invalid_token_unauthorized():
    client = TestClient(app)
    r = client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401
    assert r.json() == {"error": {"code": "UNAUTHORIZED", "message": "Authentication required."}}


def test_auth_me_expired_token_unauthorized():
    client = TestClient(app)
    token = create_access_token(
        "admin",
        username="admin",
        role="administrator",
        secret=os.environ["AUTH_TOKEN_SECRET"],
        expires_minutes=1,
        now=datetime(2000, 1, 1, tzinfo=timezone.utc),
    )
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert r.json() == {"error": {"code": "UNAUTHORIZED", "message": "Authentication required."}}

