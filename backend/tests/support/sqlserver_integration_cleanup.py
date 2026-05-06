"""Pytest helpers: wipe SQL Server business tables on the configured test database."""

from __future__ import annotations

import logging

from src.database.sqlserver_business_data_cleanup import (
    run_delete_pipeline,
    validate_critical_tables_empty,
)
from src.env_settings.sqlserver_resolution import resolve_sqlserver_connection_config

logger = logging.getLogger(__name__)


def sqlserver_test_connection_configured() -> bool:
    return bool(resolve_sqlserver_connection_config().connection_string.strip())


def cleanup_sqlserver_test_business_data(connection_string: str) -> None:
    """Delete domain rows within one transaction; raises if verification finds leftovers."""
    try:
        import pyodbc
    except ImportError as exc:
        raise RuntimeError("pyodbc required for SQL Server test cleanup") from exc

    conn = pyodbc.connect(connection_string, autocommit=False)
    try:
        cur = conn.cursor()
        run_delete_pipeline(cur)
        validate_critical_tables_empty(cur)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
