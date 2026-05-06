"""Pytest wiring: load ``.env.test`` overrides then enforce SQL Server test-database safety."""

from __future__ import annotations

from pathlib import Path


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
        import pytest

        pytest.exit(str(exc), returncode=2)
