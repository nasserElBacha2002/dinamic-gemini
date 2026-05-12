"""Phase A2: migration 0025 adds client_suppliers foundation table."""

from __future__ import annotations

from pathlib import Path


def test_migration_0025_exists_and_creates_client_suppliers_table() -> None:
    root = Path(__file__).resolve().parents[2]
    mig = root / "src/database/migrations/versions/0025_client_suppliers_foundation.sql"
    assert mig.is_file(), "0025_client_suppliers_foundation.sql must exist"
    text = mig.read_text(encoding="utf-8").lower()
    assert "create table client_suppliers" in text
    assert "fk_client_suppliers_client" in text
    assert "uq_client_suppliers_client_name" in text
    assert "ix_client_suppliers_client_id" in text


def test_schema_sql_contains_client_suppliers_foundation_section() -> None:
    root = Path(__file__).resolve().parents[2]
    schema = root / "src/database/schema.sql"
    text = schema.read_text(encoding="utf-8").lower()
    assert "phase a2 — client suppliers foundation" in text
    assert "create table client_suppliers" in text

