"""Phase D9 correction: migration 0032 removes global prompt table and fixes supplier scope keys."""

from __future__ import annotations

from pathlib import Path


def test_migration_0032_exists_and_contains_corrections() -> None:
    root = Path(__file__).resolve().parents[2]
    migration = (
        root / "src/database/migrations/versions/0032_supplier_prompt_scope_correction.sql"
    )
    assert migration.is_file(), "0032_supplier_prompt_scope_correction.sql must exist"
    text = migration.read_text(encoding="utf-8").lower()
    assert "drop table global_prompt_configs" in text
    assert "alter table supplier_prompt_configs alter column provider_name varchar(32) null" in text
    assert "#all_providers#" in text
    assert "#all_models#" in text
    assert "ck_supplier_prompt_configs_valid_scope" in text
