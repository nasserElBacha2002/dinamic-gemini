"""Shared API test setup: v3 routes require an authenticated admin."""

from __future__ import annotations

import pytest

from src.api.server import app
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser


def _fake_admin() -> AuthUser:
    return AuthUser(id="admin", username="admin", role="administrator")


@pytest.fixture(autouse=True)
def _override_v3_admin_auth() -> None:
    app.dependency_overrides[get_current_admin] = _fake_admin
    yield
    app.dependency_overrides.pop(get_current_admin, None)
