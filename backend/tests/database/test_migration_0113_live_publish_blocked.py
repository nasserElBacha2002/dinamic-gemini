"""Migration 0113 — publish block columns."""

from __future__ import annotations

from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[2] / "src" / "database" / "migrations" / "versions"


def test_migration_0113_sql_adds_publish_blocked() -> None:
    sql = (MIGRATIONS / "0113_din508_live_publish_blocked.sql").read_text(encoding="utf-8")
    assert "publish_blocked_at" in sql
    assert "publish_blocked_by_principal_id" in sql
    assert "aisle_live_channel_credentials" in sql
