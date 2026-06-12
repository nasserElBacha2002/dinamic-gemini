"""Explicit SQL Server transaction for multi-statement job-result persistence."""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pyodbc

logger = logging.getLogger(__name__)

try:
    import pyodbc as _pyodbc
except ImportError:
    _pyodbc = None  # type: ignore


class SqlServerTransaction:
    """One connection with manual commit/rollback (no per-statement autocommit)."""

    def __init__(self, connection_string: str) -> None:
        if _pyodbc is None:
            raise RuntimeError("pyodbc is not installed")
        self._connection_string = connection_string.strip()
        self._conn: pyodbc.Connection | None = None
        self._cursor: pyodbc.Cursor | None = None

    @property
    def connection(self) -> pyodbc.Connection:
        if self._conn is None:
            raise RuntimeError("SqlServerTransaction is not active")
        return self._conn

    @property
    def active_cursor(self) -> Any:
        if self._cursor is None:
            raise RuntimeError("SqlServerTransaction is not active")
        return self._cursor

    @contextmanager
    def cursor(self) -> Generator[Any, None, None]:
        if self._cursor is None:
            raise RuntimeError("SqlServerTransaction is not active")
        yield self._cursor

    def __enter__(self) -> SqlServerTransaction:
        self._conn = _pyodbc.connect(self._connection_string)
        self._conn.autocommit = False
        self._cursor = self._conn.cursor()
        return self

    def commit(self) -> None:
        if self._conn is not None:
            self._conn.commit()
            logger.debug("SqlServerTransaction committed")

    def rollback(self) -> None:
        if self._conn is not None:
            try:
                self._conn.rollback()
                logger.warning("SqlServerTransaction rolled back")
            except Exception:
                logger.exception("SqlServerTransaction rollback failed")

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            self.rollback()
        try:
            if self._cursor is not None:
                self._cursor.close()
        finally:
            self._cursor = None
        if self._conn is not None:
            try:
                self._conn.close()
            finally:
                self._conn = None


@contextmanager
def sql_repository_cursor(
    client: Any,
    *,
    connection: Any | None = None,
) -> Generator[Any, None, None]:
    """Yield a cursor; use shared transaction connection when provided."""
    if connection is not None:
        yield connection.cursor()
        return
    with client.cursor() as cur:
        yield cur
