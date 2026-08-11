"""Unit tests for SqlServerTransaction lifecycle (mocked pyodbc connection)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.infrastructure.database.sql_transaction import SqlServerTransaction, TransactionState


@pytest.fixture
def fake_connection() -> MagicMock:
    conn = MagicMock(name="connection")
    conn.autocommit = True
    return conn


@pytest.fixture
def connect(fake_connection: MagicMock):
    with patch(
        "src.infrastructure.database.sql_transaction._pyodbc.connect",
        return_value=fake_connection,
    ) as mock_connect:
        yield mock_connect, fake_connection


def test_exception_triggers_rollback_via_exit(connect) -> None:
    _mock_connect, conn = connect
    with pytest.raises(ValueError, match="boom"):
        with SqlServerTransaction("Driver=Fake;") as txn:
            assert txn.state == TransactionState.ACTIVE
            raise ValueError("boom")
    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()
    conn.close.assert_called_once()


def test_forgotten_commit_rolls_back_on_exit(connect) -> None:
    _mock_connect, conn = connect
    with SqlServerTransaction("Driver=Fake;") as txn:
        assert txn.state == TransactionState.ACTIVE
    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()
    conn.close.assert_called_once()


def test_commit_prevents_second_rollback_on_exit(connect) -> None:
    _mock_connect, conn = connect
    with SqlServerTransaction("Driver=Fake;") as txn:
        txn.commit()
        assert txn.state == TransactionState.COMMITTED
    conn.commit.assert_called_once()
    conn.rollback.assert_not_called()
    conn.close.assert_called_once()


def test_explicit_rollback_then_close_is_safe(connect) -> None:
    _mock_connect, conn = connect
    with SqlServerTransaction("Driver=Fake;") as txn:
        txn.rollback()
        assert txn.state == TransactionState.ROLLED_BACK
    conn.rollback.assert_called_once()
    conn.close.assert_called_once()

    conn.reset_mock()
    txn2 = SqlServerTransaction("Driver=Fake;")
    with txn2:
        txn2.rollback()
    conn.rollback.assert_called_once()
    conn.close.assert_called_once()
