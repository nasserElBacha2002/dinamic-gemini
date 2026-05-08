"""Phase D9: migration 0031 adds global_prompt_configs foundation."""

from __future__ import annotations

from pathlib import Path


def test_migration_0031_exists_and_adds_global_prompt_configs_table() -> None:
    root = Path(__file__).resolve().parents[2]
    migration = (
        root / "src/database/migrations/versions/0031_global_prompt_configs_foundation.sql"
    )
    assert migration.is_file(), "0031_global_prompt_configs_foundation.sql must exist"
    text = migration.read_text(encoding="utf-8").lower()
    assert "create table global_prompt_configs" in text
    assert "ck_global_prompt_configs_scope_type_global" in text
    assert "ck_global_prompt_configs_global_null_provider_model" in text
    assert (
        "model_scope_key as (case when model_name is null then '#null#' else 'm:' + model_name end) persisted"
        in text
    )
    assert "uq_global_prompt_configs_scope_version" in text
    assert "uq_global_prompt_configs_one_active" in text


def test_schema_sql_contains_global_prompt_configs_section() -> None:
    root = Path(__file__).resolve().parents[2]
    schema = root / "src/database/schema.sql"
    text = schema.read_text(encoding="utf-8").lower()
    assert "create table global_prompt_configs" in text
    assert "ck_global_prompt_configs_scope_type_global" in text
    assert "ck_global_prompt_configs_global_null_provider_model" in text
    assert (
        "model_scope_key as (case when model_name is null then '#null#' else 'm:' + model_name end) persisted"
        in text
    )
    assert "uq_global_prompt_configs_scope_version" in text
    assert "uq_global_prompt_configs_one_active" in text
