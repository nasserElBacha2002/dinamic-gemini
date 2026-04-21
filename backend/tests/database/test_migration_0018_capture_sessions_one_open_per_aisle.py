"""Sprint 2 hardening: migration 0018 adds filtered unique index for one open capture session per aisle."""

from __future__ import annotations

from pathlib import Path


def test_migration_0018_exists_and_defines_filtered_unique_index() -> None:
    root = Path(__file__).resolve().parents[2]
    mig = root / "src/database/migrations/versions/0018_capture_sessions_one_open_per_aisle.sql"
    assert mig.is_file(), "0018_capture_sessions_one_open_per_aisle.sql must exist"
    text = mig.read_text(encoding="utf-8").lower()
    assert "capture_sessions" in text
    assert "uq_capture_sessions_one_open_per_aisle" in text
    assert "unique" in text
    assert "open_ranked" in text, "migration should dedupe open sessions before creating unique index"
