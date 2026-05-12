"""Phase C9: migration 0029 drops deprecated inventory_visual_references."""

from __future__ import annotations

from pathlib import Path


def test_migration_0029_exists_and_is_guarded() -> None:
    root = Path(__file__).resolve().parents[2]
    migration = root / "src/database/migrations/versions/0029_drop_inventory_visual_references.sql"
    assert migration.is_file(), "0029_drop_inventory_visual_references.sql must exist"
    text = migration.read_text(encoding="utf-8").lower()
    assert "drop table inventory_visual_references" in text
    assert "if exists (select 1 from inventory_visual_references)" in text
    assert "throw 51029" in text


def test_schema_sql_has_no_inventory_visual_references_table() -> None:
    root = Path(__file__).resolve().parents[2]
    schema = root / "src/database/schema.sql"
    text = schema.read_text(encoding="utf-8").lower()
    assert "create table inventory_visual_references" not in text
