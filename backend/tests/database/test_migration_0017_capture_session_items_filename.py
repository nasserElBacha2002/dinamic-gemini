"""Sprint 2: migration 0017 adds optional original_filename on capture_session_items."""

from __future__ import annotations

from pathlib import Path


def test_migration_0017_exists_and_alters_items_table() -> None:
    root = Path(__file__).resolve().parents[2]
    mig = root / "src/database/migrations/versions/0017_capture_session_items_original_filename.sql"
    assert mig.is_file(), "0017_capture_session_items_original_filename.sql must exist"
    text = mig.read_text(encoding="utf-8").lower()
    assert "capture_session_items" in text
    assert "original_filename" in text
    assert "alter table" in text
