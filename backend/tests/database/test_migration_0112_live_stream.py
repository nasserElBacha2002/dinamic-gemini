"""Migration 0112 — live stream grants and channel credentials."""

from __future__ import annotations

from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[2] / "src" / "database" / "migrations" / "versions"


def test_migration_0112_sql_contains_tables() -> None:
    sql = (MIGRATIONS / "0112_din508_live_stream_grants.sql").read_text(encoding="utf-8")
    assert "aisle_live_channel_credentials" in sql
    assert "aisle_live_view_grants" in sql
    assert "token_hash" in sql
    assert "publish_password_hash" in sql