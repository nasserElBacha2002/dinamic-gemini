"""Phase D1: migration 0030 adds supplier_prompt_configs foundation."""

from __future__ import annotations

from pathlib import Path


def test_migration_0030_exists_and_adds_supplier_prompt_configs_table() -> None:
    root = Path(__file__).resolve().parents[2]
    migration = (
        root / "src/database/migrations/versions/0030_supplier_prompt_configs_foundation.sql"
    )
    assert migration.is_file(), "0030_supplier_prompt_configs_foundation.sql must exist"
    text = migration.read_text(encoding="utf-8").lower()
    assert "create table supplier_prompt_configs" in text
    assert "fk_supplier_prompt_configs_client_supplier" in text
    assert (
        "model_scope_key as (case when model_name is null then '#null#' else 'm:' + model_name end) persisted"
        in text
    )
    assert "uq_supplier_prompt_configs_scope_version" in text
    assert "uq_supplier_prompt_configs_one_active" in text


def test_schema_sql_contains_supplier_prompt_configs_section() -> None:
    root = Path(__file__).resolve().parents[2]
    schema = root / "src/database/schema.sql"
    text = schema.read_text(encoding="utf-8").lower()
    assert "create table supplier_prompt_configs" in text
    assert "fk_supplier_prompt_configs_client_supplier" in text
    assert "provider_scope_key as (case when provider_name is null then '#all_providers#'" in text
    assert (
        "model_scope_key as (case when model_name is null then '#all_models#' else 'm:' + model_name end) persisted"
        in text
    )
    assert "ck_supplier_prompt_configs_valid_scope" in text
    assert "uq_supplier_prompt_configs_scope_version" in text
    assert "uq_supplier_prompt_configs_one_active" in text
