"""Phase A4: migration 0027 adds nullable aisles.client_supplier_id foundation."""

from __future__ import annotations

from pathlib import Path


def test_migration_0027_exists_and_adds_nullable_aisle_client_supplier_id() -> None:
    root = Path(__file__).resolve().parents[2]
    mig = root / "src/database/migrations/versions/0027_aisles_nullable_client_supplier_id.sql"
    assert mig.is_file(), "0027_aisles_nullable_client_supplier_id.sql must exist"
    text = mig.read_text(encoding="utf-8").lower()
    assert "alter table aisles add client_supplier_id" in text
    assert "fk_aisles_client_supplier" in text
    assert "ix_aisles_client_supplier_id" in text


def test_schema_sql_contains_aisles_nullable_client_supplier_id_section() -> None:
    root = Path(__file__).resolve().parents[2]
    schema = root / "src/database/schema.sql"
    text = schema.read_text(encoding="utf-8").lower()
    assert "alter table aisles add client_supplier_id" in text
    assert "fk_aisles_client_supplier" in text

