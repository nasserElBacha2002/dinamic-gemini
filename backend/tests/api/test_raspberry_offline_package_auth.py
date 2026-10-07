"""Authorization for GET /api/v3/clients/raspberry-offline-package."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from passlib.context import CryptContext

import src.config as config_module
from src.api.deps.inventory import get_export_raspberry_offline_package_use_case
from src.api.dependencies import get_client_repo
from src.api.server import app
from src.application.use_cases.clients.get_raspberry_recognition_config import (
    OfflineRaspberryRecognitionBundle,
)
from src.auth.dependencies import get_current_admin
from src.auth.security import create_access_token
from src.config import reload_settings
from src.domain.client.entities import Client, ClientStatus
from src.infrastructure.repositories.memory_client_repository import MemoryClientRepository

_PWD = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
_SECRET = "t" * 40
_PATH = "/api/v3/clients/raspberry-offline-package"


@pytest.fixture()
def auth_env(monkeypatch: pytest.MonkeyPatch):
    import os

    tracked = (
        "SQLSERVER_ENABLED",
        "ADMIN_USERNAME",
        "ADMIN_PASSWORD_HASH",
        "AUTH_TOKEN_SECRET",
        "AUTH_TOKEN_EXPIRES_MINUTES",
    )
    prior_env = {key: os.environ.get(key) for key in tracked}
    monkeypatch.setattr(config_module, "_load_dotenv_files", lambda for_reload=False: None)
    monkeypatch.setenv("SQLSERVER_ENABLED", "false")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", _PWD.hash("correct-password"))
    monkeypatch.setenv("AUTH_TOKEN_SECRET", _SECRET)
    monkeypatch.setenv("AUTH_TOKEN_EXPIRES_MINUTES", "30")
    reload_settings()
    app.dependency_overrides.pop(get_current_admin, None)
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
        app.dependency_overrides.pop(get_client_repo, None)
        app.dependency_overrides.pop(get_export_raspberry_offline_package_use_case, None)
        for key, val in prior_env.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
        reload_settings()


def _token(*, role: str, client_id: str | None) -> str:
    return create_access_token(
        "admin",
        username="lab",
        role=role,
        principal_id="u1",
        client_id=client_id,
        secret=_SECRET,
        expires_minutes=30,
    )


def _seed_clients() -> MemoryClientRepository:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clients = MemoryClientRepository()
    for cid, name in (("client-a", "A"), ("client-b", "B")):
        clients.save(
            Client(
                id=cid,
                name=name,
                status=ClientStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )
    return clients


def _mock_export_use_case() -> MagicMock:
    use_case = MagicMock()
    recognition = OfflineRaspberryRecognitionBundle(
        bundle_schema_version=1,
        generated_at=datetime.now(timezone.utc),
        clients=(),
        bundle_revision="rev-test",
    )
    result = MagicMock()
    result.package_schema_version = 1
    result.generated_at = datetime.now(timezone.utc)
    result.recognition = recognition
    result.inventories = ()
    result.inventory_recognition_configs = ()
    use_case.execute.return_value = result
    return use_case


def test_raspberry_offline_package_requires_auth(auth_env) -> None:
    client = TestClient(app)
    assert client.get(_PATH).status_code == 401


def test_company_admin_cannot_export_all_clients(auth_env) -> None:
    clients = _seed_clients()
    app.dependency_overrides[get_client_repo] = lambda: clients
    app.dependency_overrides[get_export_raspberry_offline_package_use_case] = (
        lambda: _mock_export_use_case()
    )
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {_token(role='company_admin', client_id='client-a')}"}
    assert client.get(_PATH, headers=headers).status_code == 403


def test_company_admin_cannot_export_other_client(auth_env) -> None:
    clients = _seed_clients()
    app.dependency_overrides[get_client_repo] = lambda: clients
    app.dependency_overrides[get_export_raspberry_offline_package_use_case] = (
        lambda: _mock_export_use_case()
    )
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {_token(role='company_admin', client_id='client-a')}"}
    assert (
        client.get(_PATH, params={"client_id": "client-b"}, headers=headers).status_code == 404
    )


def test_company_admin_can_export_own_client(auth_env) -> None:
    clients = _seed_clients()
    app.dependency_overrides[get_client_repo] = lambda: clients
    app.dependency_overrides[get_export_raspberry_offline_package_use_case] = (
        lambda: _mock_export_use_case()
    )
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {_token(role='company_admin', client_id='client-a')}"}
    response = client.get(_PATH, params={"client_id": "client-a"}, headers=headers)
    assert response.status_code == 200
    assert response.headers.get("content-disposition", "").startswith("attachment")


def test_platform_admin_can_export_all(auth_env) -> None:
    clients = _seed_clients()
    app.dependency_overrides[get_client_repo] = lambda: clients
    app.dependency_overrides[get_export_raspberry_offline_package_use_case] = (
        lambda: _mock_export_use_case()
    )
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {_token(role='platform_admin', client_id=None)}"}
    assert client.get(_PATH, headers=headers).status_code == 200
