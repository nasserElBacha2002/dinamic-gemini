"""Smoke: migration 0065 SQL file exists and is additive."""

from __future__ import annotations

from pathlib import Path


def test_migration_0065_file_exists_and_creates_table():
    path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "database"
        / "migrations"
        / "versions"
        / "0065_authoritative_local_code_scan_results.sql"
    )
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "authoritative_local_code_scan_results" in text
    assert "UQ_alcsr_asset_version" in text
    assert "LOCAL_CODE_SCAN" in text
    assert "SERVER_CODE_SCAN" not in text.split("CK_alcsr_source")[1].split("GO")[0]
    assert "client_confirmed_at" in text
    assert "server_confirmed_at" in text
    assert "ADD confirmed_result_id" not in text
    assert "DROP TABLE" not in text.split("Formal rollback")[0]


def test_migration_0065_does_not_drop_reconciliations():
    path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "database"
        / "migrations"
        / "versions"
        / "0065_authoritative_local_code_scan_results.sql"
    )
    text = path.read_text(encoding="utf-8")
    assert "DROP TABLE preliminary_detection_reconciliations" not in text
    assert "DROP TABLE mobile_preliminary_detections" not in text
