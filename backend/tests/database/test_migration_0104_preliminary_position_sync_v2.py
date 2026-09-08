"""Smoke tests for additive preliminary position sync V2 migration."""

from __future__ import annotations

from pathlib import Path


def test_migration_0104_adds_diagnostic_position_fields_only():
    path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "database"
        / "migrations"
        / "versions"
        / "0104_preliminary_position_sync_v2.sql"
    )
    text = path.read_text(encoding="utf-8")

    assert "position_local_recognition_id" in text
    assert "position_result_status" in text
    assert "position_reconciliation_revision" in text
    assert "ALTER TABLE dbo.mobile_preliminary_detections ADD" in text
    assert "INSERT INTO positions" not in text
    assert "UPDATE positions" not in text
    assert "DROP TABLE" not in text
