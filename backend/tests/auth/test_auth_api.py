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
    monkeypatch.setenv("AUTH_REFRESH_TOKEN_EXPIRES_MINUTES", "43200")
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
    # v3.2.3.E6: login also returns refresh_token and refresh_expires_in.
    assert isinstance(data.get("refresh_token"), str) and data["refresh_token"]
    assert isinstance(data.get("refresh_expires_in"), int) and data["refresh_expires_in"] > 0
    assert data["user"]["id"] == "admin"
    assert data["user"]["username"] == "admin"
    assert data["user"]["role"] == "administrator"


def test_auth_refresh_issues_new_tokens_and_rotates_refresh():
    client = TestClient(app)
    login_r = client.post("/auth/login", json={"username": "admin", "password": "correct-password"})
    assert login_r.status_code == 200
    login_data = login_r.json()
    old_access = login_data["access_token"]
    old_refresh = login_data["refresh_token"]

    refresh_r = client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert refresh_r.status_code == 200
    refresh_data = refresh_r.json()
    assert refresh_data["access_token"] != old_access
    assert refresh_data["refresh_token"] != old_refresh

    # Old refresh token is now invalid.
    refresh_r2 = client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert refresh_r2.status_code == 401
    assert refresh_r2.json() == {"error": {"code": "UNAUTHORIZED", "message": "Authentication required."}}


def test_auth_logout_revokes_refresh_token():
    client = TestClient(app)
    login_r = client.post("/auth/login", json={"username": "admin", "password": "correct-password"})
    assert login_r.status_code == 200
    login_data = login_r.json()
    access = login_data["access_token"]
    refresh = login_data["refresh_token"]

    # Logout with valid access + refresh.
    logout_r = client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {access}"},
        json={"refresh_token": refresh},
    )
    assert logout_r.status_code == 204

    # Logged-out refresh token cannot be used anymore.
    refresh_r = client.post("/auth/refresh", json={"refresh_token": refresh})
    assert refresh_r.status_code == 401
    assert refresh_r.json() == {"error": {"code": "UNAUTHORIZED", "message": "Authentication required."}}


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

