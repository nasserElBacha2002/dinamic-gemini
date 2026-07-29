"""Shared API test setup: v3 routes require an authenticated admin."""

from __future__ import annotations

from collections.abc import Generator

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


@pytest.fixture(autouse=True, scope="module")
def _wipe_isolated_test_db_around_api_modules() -> Generator[None, None, None]:
    """API wiring tests create clients via TestClient; wipe the isolated test DB around modules.

    Only runs when pytest is pointed at an allowlisted test database (see ``.env.test``).
    Never touches developer DBs such as ``dinamic-gemini``.
    """
    from src.env_settings.sqlserver_pytest_policy import (
        sqlserver_database_is_allowed_for_tests,
        sqlserver_integration_auto_cleanup_enabled,
    )
    from src.env_settings.sqlserver_resolution import (
        resolve_sqlserver_connection_config,
        resolved_sqlserver_database_name_from_env,
    )

    if not sqlserver_integration_auto_cleanup_enabled():
        yield
        return
    db = resolved_sqlserver_database_name_from_env()
    if not db or not sqlserver_database_is_allowed_for_tests(db):
        yield
        return
    cs = resolve_sqlserver_connection_config().connection_string.strip()
    if not cs:
        yield
        return

    from tests.support.sqlserver_integration_cleanup import cleanup_sqlserver_test_business_data

    cleanup_sqlserver_test_business_data(cs)
    yield
    cleanup_sqlserver_test_business_data(cs)
