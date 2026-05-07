"""Phase C1: migration 0028 adds supplier_reference_images foundation."""

from __future__ import annotations

from pathlib import Path


def test_migration_0028_exists_and_adds_supplier_reference_images_table() -> None:
    root = Path(__file__).resolve().parents[2]
    migration = (
        root / "src/database/migrations/versions/0028_supplier_reference_images.sql"
    )
    assert migration.is_file(), "0028_supplier_reference_images.sql must exist"
    text = migration.read_text(encoding="utf-8").lower()
    assert "create table supplier_reference_images" in text
    assert "fk_supplier_reference_images_client_supplier" in text
    assert "ix_supplier_reference_images_client_supplier_id" in text


def test_schema_sql_contains_supplier_reference_images_section() -> None:
    root = Path(__file__).resolve().parents[2]
    schema = root / "src/database/schema.sql"
    text = schema.read_text(encoding="utf-8").lower()
    assert "create table supplier_reference_images" in text
    assert "fk_supplier_reference_images_client_supplier" in text
