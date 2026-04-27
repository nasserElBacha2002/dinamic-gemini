"""Helpers for SQL Server integration tests — skip fast when DB is unreachable."""

from __future__ import annotations

import pytest

from src.database.sqlserver import SqlServerClient


def _with_connect_timeout(connection_string: str, seconds: int = 5) -> str:
    """Append a short ODBC connect timeout so unreachable hosts fail fast in tests."""
    cs = connection_string.strip()
    low = cs.lower()
    if "connect timeout" in low or "connection timeout" in low:
        return cs
    return f"{cs};Connect Timeout={seconds}" if cs else cs


def sql_server_client_or_skip(connection_string: str) -> SqlServerClient:
    """Return a client or skip tests when SQL Server is missing or unreachable."""
    if not connection_string:
        pytest.skip(
            "SQL Server not configured (set SQLSERVER_CONNECTION_STRING or server/database/uid/pwd)"
        )
    client = SqlServerClient(_with_connect_timeout(connection_string))
    try:
        with client.cursor() as cur:
            cur.execute("SELECT 1")
    except Exception as exc:
        pytest.skip(f"SQL Server not reachable: {exc}")
    return client
