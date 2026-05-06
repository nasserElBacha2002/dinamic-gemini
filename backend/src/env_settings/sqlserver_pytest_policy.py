"""Safety policy: pytest and other automation must not write to a developer production/local DB.

Uses explicit database-name markers (or an allow-list) so accidental shared ``.env`` cannot
silently pollute a real database during ``pytest``.
"""

from __future__ import annotations

import os
import re

from src.env_settings.sqlserver_resolution import resolved_sqlserver_database_name_from_env

_UNSAFE_SUBSTRINGS = (
    "prod",
    "production",
    "live",
    "prd",
    "stg",
    "staging",
    "demo",
    "uat",
)
_TEST_NAME_RE = re.compile(
    r"(?i)(^|[_/])test([_/]|$)|pytest|(^|[_/])testing([_/]|$)|_test$|^test[_/]"
)


def _explicit_allowlist() -> frozenset[str]:
    raw = (os.getenv("DINAMIC_PYTEST_SQLSERVER_DATABASE_ALLOWLIST") or "").strip()
    if not raw:
        return frozenset()
    return frozenset(x.strip().lower() for x in raw.split(",") if x.strip())


def sqlserver_database_is_allowed_for_tests(database: str) -> bool:
    """Return True when ``database`` is explicitly marked as a test/automation database."""
    d = database.strip().lower()
    if not d:
        return False
    if d in _explicit_allowlist():
        return True
    if _TEST_NAME_RE.search(d):
        return True
    if "pytest" in d:
        return True
    return False


def sqlserver_database_looks_unsafe_for_tests(database: str) -> bool:
    """Heuristic block-list for names that often indicate non-local operational databases."""
    d = database.strip().lower()
    return any(s in d for s in _UNSAFE_SUBSTRINGS)


def assert_pytest_sqlserver_database_is_safe() -> None:
    """Raise ``RuntimeError`` when SQL Server is configured with a non-test database name.

    Set ``DINAMIC_PYTEST_ALLOW_NON_TEST_SQLSERVER=1`` only as an explicit escape hatch (e.g. rare
    debugging). Prefer a dedicated test database and ``backend/.env.test`` instead.
    """
    if (os.getenv("DINAMIC_PYTEST_ALLOW_NON_TEST_SQLSERVER") or "").strip() == "1":
        return
    db = resolved_sqlserver_database_name_from_env()
    if db is None:
        return
    dnorm = db.strip().lower()
    if dnorm in _explicit_allowlist():
        return
    if sqlserver_database_looks_unsafe_for_tests(db):
        raise RuntimeError(
            "Refusing to run pytest: SQL Server database name matches a blocked operational pattern "
            f"({db!r}). Use a dedicated test database or add an exact name to "
            "DINAMIC_PYTEST_SQLSERVER_DATABASE_ALLOWLIST. "
            "Override only with DINAMIC_PYTEST_ALLOW_NON_TEST_SQLSERVER=1."
        )
    if not sqlserver_database_is_allowed_for_tests(db):
        raise RuntimeError(
            "Refusing to run pytest: SQL Server is configured but database name does not look like "
            f"a test database ({db!r}). Use backend/.env.test with SQLSERVER_DATABASE=myapp_test "
            "(or SQLSERVER_CONNECTION_STRING with DATABASE=…test…) "
            "or set DINAMIC_PYTEST_SQLSERVER_DATABASE_ALLOWLIST. "
            "Override only with DINAMIC_PYTEST_ALLOW_NON_TEST_SQLSERVER=1."
        )
