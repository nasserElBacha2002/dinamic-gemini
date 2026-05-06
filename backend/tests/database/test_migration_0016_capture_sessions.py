"""Sprint 1: capture session DDL is present in the versioned migration chain."""

from __future__ import annotations

from pathlib import Path


def test_migration_0016_exists_and_defines_capture_tables() -> None:
    root = Path(__file__).resolve().parents[2]
    mig = root / "src/database/migrations/versions/0016_capture_sessions.sql"
    assert mig.is_file(), "0016_capture_sessions.sql must exist"
    text = mig.read_text(encoding="utf-8").lower()
    assert "create table capture_sessions" in text
    assert "create table capture_session_items" in text
    assert "create table capture_session_confirmations" in text
    assert "alter table source_assets" not in text
