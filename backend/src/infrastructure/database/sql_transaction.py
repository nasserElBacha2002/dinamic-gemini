"""Explicit SQL Server transaction for multi-statement job-result persistence."""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pyodbc

logger = logging.getLogger(__name__)

try:
    import pyodbc as _pyodbc
except ImportError:
    _pyodbc = None  # type: ignore


class TransactionState(str, Enum):
    ACTIVE = "active"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"
    CLOSED = "closed"


class SqlServerTransaction:
    """One connection with explicit commit/rollback lifecycle (UoW-owned outcome)."""

    def __init__(self, connection_string: str) -> None:
        if _pyodbc is None:
            raise RuntimeError("pyodbc is not installed")
        self._connection_string = connection_string.strip()
        self._conn: pyodbc.Connection | None = None
        self._state = TransactionState.CLOSED

    @property
    def connection(self) -> pyodbc.Connection:
        if self._conn is None or self._state == TransactionState.CLOSED:
            raise RuntimeError("SqlServerTransaction is not active")
        return self._conn

    @property
    def state(self) -> TransactionState:
        return self._state

    def __enter__(self) -> SqlServerTransaction:
        if self._state != TransactionState.CLOSED:
            raise RuntimeError("SqlServerTransaction is already active")
        self._conn = _pyodbc.connect(self._connection_string)
        self._conn.autocommit = False
        self._state = TransactionState.ACTIVE
        return self

    def commit(self) -> None:
        if self._state != TransactionState.ACTIVE:
            raise RuntimeError(f"Cannot commit transaction in state {self._state.value}")
        assert self._conn is not None
        self._conn.commit()
        self._state = TransactionState.COMMITTED
        logger.debug("SqlServerTransaction committed")

    def rollback(self) -> None:
        if self._state in (TransactionState.ROLLED_BACK, TransactionState.COMMITTED):
            return
        if self._state == TransactionState.CLOSED:
            return
        if self._state != TransactionState.ACTIVE:
            raise RuntimeError(f"Cannot rollback transaction in state {self._state.value}")
        if self._conn is None:
            self._state = TransactionState.ROLLED_BACK
            return
        try:
            self._conn.rollback()
            logger.warning("SqlServerTransaction rolled back")
        except Exception:
            logger.exception("SqlServerTransaction rollback failed")
            raise
        finally:
            self._state = TransactionState.ROLLED_BACK

    def close(self) -> None:
        if self._state == TransactionState.CLOSED:
            return
        if self._conn is not None:
            try:
                self._conn.close()
            finally:
                self._conn = None
        self._state = TransactionState.CLOSED

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


@contextmanager
def sql_repository_cursor(
    client: Any,
    *,
    connection: Any | None = None,
) -> Generator[Any, None, None]:
    """Yield a cursor; use shared transaction connection when provided."""
    if connection is not None:
        cursor = connection.cursor()
        try:
            yield cursor
        finally:
            cursor.close()
        return
    with client.cursor() as cur:
        yield cur
