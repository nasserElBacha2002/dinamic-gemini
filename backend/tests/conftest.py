"""Pytest wiring: load ``.env.test`` overrides then enforce SQL Server test-database safety."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest


def _bootstrap_dotenv_for_pytest() -> None:
    """Load repo/backend ``.env``, then ``.env.test`` with override (local test DB isolation)."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    here = Path(__file__).resolve()
    backend = here.parents[1]
    repo = here.parents[2]
    load_dotenv(repo / ".env", override=False)
    load_dotenv(backend / ".env", override=False)
    load_dotenv(repo / ".env.test", override=True)
    load_dotenv(backend / ".env.test", override=True)


# Import-time bootstrap runs before deeper ``conftest`` files import ``src.*`` (so cached Settings
# see test DB env, not only developer ``.env``).
_bootstrap_dotenv_for_pytest()


def pytest_configure(config: object) -> None:
    from src.env_settings.sqlserver_pytest_policy import assert_pytest_sqlserver_database_is_safe

    try:
        assert_pytest_sqlserver_database_is_safe()
    except RuntimeError as exc:
        pytest.exit(str(exc), returncode=2)


@pytest.fixture(autouse=True)
def _cleanup_sqlserver_integration_business_data(
    request: pytest.FixtureRequest,
) -> Generator[None, None, None]:
    """Wipe SQL Server business rows around each integration test when using an isolated test DB."""
    if request.node.get_closest_marker("integration") is None:
        yield
        return

    from src.env_settings.sqlserver_pytest_policy import sqlserver_integration_auto_cleanup_enabled
    from src.env_settings.sqlserver_resolution import resolve_sqlserver_connection_config

    if not sqlserver_integration_auto_cleanup_enabled():
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
