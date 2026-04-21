"""Sprint 3: migration 0019 adds clock offset + preview columns."""

from __future__ import annotations

from pathlib import Path


def test_migration_0019_exists_and_adds_columns() -> None:
    root = Path(__file__).resolve().parents[2]
    mig = root / "src/database/migrations/versions/0019_capture_session_sprint3_preview.sql"
    assert mig.is_file(), "0019_capture_session_sprint3_preview.sql must exist"
    text = mig.read_text(encoding="utf-8").lower()
    assert "clock_offset_seconds" in text
    assert "adjusted_capture_time" in text
    assert "assignment_reason" in text
    assert "preview_target_position_id" in text
