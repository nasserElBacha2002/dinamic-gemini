"""Stage 8 — SQL Server client using pyodbc (parameterized queries, context manager)."""

import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator, Optional

logger = logging.getLogger(__name__)

try:
    import pyodbc
except ImportError:
    pyodbc = None  # type: ignore


def now_utc() -> datetime:
    """Current UTC time for DB datetime2 columns."""
    return datetime.now(timezone.utc)


class SqlServerClient:
    """SQL Server client: connect via ODBC, provide cursor context manager."""

    def __init__(self, connection_string: str) -> None:
        if not connection_string or not connection_string.strip():
            raise ValueError(
                "connection_string is required. Configure SQLSERVER_CONNECTION_STRING or "
                "SQLSERVER_SERVER, SQLSERVER_DATABASE, SQLSERVER_UID, SQLSERVER_PWD "
                "(and SQLSERVER_DRIVER if no ODBC driver is auto-detected)."
            )
        if pyodbc is None:
            raise RuntimeError("pyodbc is not installed; install with: pip install pyodbc")
        self._connection_string = connection_string.strip()

    @contextmanager
    def cursor(self) -> Generator["pyodbc.Cursor", None, None]:
        """Yield a cursor; connection is closed on exit. Commits on success, rolls back on exception."""
        conn: Optional[pyodbc.Connection] = None
        try:
            conn = pyodbc.connect(self._connection_string)
            cur = conn.cursor()
            yield cur
            conn.commit()
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            logger.exception("SQL Server operation failed: %s", e)
            raise
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
