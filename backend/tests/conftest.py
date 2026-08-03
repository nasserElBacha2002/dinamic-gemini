"""Pytest wiring: load ``.env.test`` overrides then enforce SQL Server test-database safety."""

from __future__ import annotations

import os
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
    # Prevent ``src.config.reload_settings()`` / import-time dotenv from clobbering
    # ``.env.test`` (developer ``.env`` uses DATABASE=dinamic-gemini).
    os.environ["DINAMIC_PYTEST_DOTENV_LOCKED"] = "1"


def _ensure_pytest_identification_flags() -> None:
    """CI has no developer ``.env``; SYSTEM_DEFAULT is CODE_SCAN and needs the scan flag on.

    Unit tests that assert the disabled path pass ``code_scan_processing_enabled=False``
    (or INTERNAL_OCR flags) explicitly and do not depend on this env default.
    """
    os.environ.setdefault("CODE_SCAN_PROCESSING_ENABLED", "true")
    os.environ.setdefault("INTERNAL_OCR_PROCESSING_ENABLED", "true")
    # Production-policy tests set APP_ENV=production before reloading settings.
    # Keep signing enabled while supplying test-only key material.
    os.environ.setdefault(
        "POSITIONING_LABEL_HMAC_SECRET",
        "pytest-only-positioning-label-secret",
    )


# Import-time bootstrap runs before deeper ``conftest`` files import ``src.*`` (so cached Settings
# see test DB env, not only developer ``.env``).
_bootstrap_dotenv_for_pytest()
_ensure_pytest_identification_flags()


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
