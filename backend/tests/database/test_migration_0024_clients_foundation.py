"""Phase A1: migration 0024 adds clients foundation table."""

from __future__ import annotations

from pathlib import Path


def test_migration_0024_exists_and_creates_clients_table() -> None:
    root = Path(__file__).resolve().parents[2]
    mig = root / "src/database/migrations/versions/0024_clients_foundation.sql"
    assert mig.is_file(), "0024_clients_foundation.sql must exist"
    text = mig.read_text(encoding="utf-8").lower()
    assert "create table clients" in text
    assert "df_clients_status" in text
    assert "ix_clients_name" in text


def test_schema_sql_contains_clients_foundation_section() -> None:
    root = Path(__file__).resolve().parents[2]
    schema = root / "src/database/schema.sql"
    text = schema.read_text(encoding="utf-8").lower()
    assert "phase a1 — clients foundation" in text
    assert "create table clients" in text

