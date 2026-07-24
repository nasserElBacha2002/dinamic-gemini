"""Smoke: migration 0066 SQL file exists and is additive."""

from __future__ import annotations

from pathlib import Path


def test_migration_0066_file_exists_and_creates_tables():
    path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "database"
        / "migrations"
        / "versions"
        / "0066_authoritative_aisle_finalization.sql"
    )
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "authoritative_aisle_finalizations" in text
    assert "authoritative_aisle_finalization_items" in text
    assert "authoritative_aisle_excluded_assets" in text
    assert "authoritative_aisle_finalization_locks" in text
    assert "COMPLETED_BY_LOCAL_AUTHORITY" in text
    assert "DROP TABLE" not in text.split("Formal rollback")[0]


def test_migration_0066_does_not_alter_authoritative_results():
    path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "database"
        / "migrations"
        / "versions"
        / "0066_authoritative_aisle_finalization.sql"
    )
    text = path.read_text(encoding="utf-8")
    assert "ALTER TABLE authoritative_local_code_scan_results" not in text
