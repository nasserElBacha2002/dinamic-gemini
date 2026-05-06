"""Resolve SQL Server ODBC connection for integration tests (same rules as the running app)."""

from __future__ import annotations

from src.env_settings.sqlserver_resolution import resolve_sqlserver_connection_config


def resolved_sqlserver_connection_string_for_tests() -> str:
    """Effective ODBC connection string from env (split vars or ``SQLSERVER_CONNECTION_STRING``)."""
    return resolve_sqlserver_connection_config().connection_string.strip()
