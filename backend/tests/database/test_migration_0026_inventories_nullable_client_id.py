"""Phase A3: migration 0026 adds nullable inventories.client_id foundation."""

from __future__ import annotations

from pathlib import Path


def test_migration_0026_exists_and_adds_nullable_inventory_client_id() -> None:
    root = Path(__file__).resolve().parents[2]
    mig = root / "src/database/migrations/versions/0026_inventories_nullable_client_id.sql"
    assert mig.is_file(), "0026_inventories_nullable_client_id.sql must exist"
    text = mig.read_text(encoding="utf-8").lower()
    assert "alter table inventories add client_id" in text
    assert "fk_inventories_client" in text
    assert "ix_inventories_client_id" in text


def test_schema_sql_contains_inventories_nullable_client_id_section() -> None:
    root = Path(__file__).resolve().parents[2]
    schema = root / "src/database/schema.sql"
    text = schema.read_text(encoding="utf-8").lower()
    assert "alter table inventories add client_id" in text
    assert "fk_inventories_client" in text

