"""Observability corrections: migration 0046 adds original_filename + versioned-snapshot columns."""

from __future__ import annotations

from pathlib import Path


def _read_migration() -> str:
    root = Path(__file__).resolve().parents[2]
    migration = (
        root / "src/database/migrations/versions/0046_job_source_assets_original_filename.sql"
    )
    assert migration.is_file(), "0046_job_source_assets_original_filename.sql must exist"
    return migration.read_text(encoding="utf-8").lower()


def test_migration_0046_adds_original_filename_column() -> None:
    text = _read_migration()
    assert "add original_filename nvarchar(512) null" in text


def test_migration_0046_adds_optional_derived_asset_columns() -> None:
    text = _read_migration()
    assert "add transformation nvarchar(128) null" in text
    assert "add source_parent_id varchar(36) null" in text
    assert "add artifact_id varchar(64) null" in text
    assert "add snapshot_version int not null" in text


def test_migration_0046_adds_job_fk_and_check_constraints() -> None:
    text = _read_migration()
    assert "fk_job_source_assets_job" in text
    assert "references inventory_jobs(id) on delete cascade" in text
    assert "ck_job_source_assets_position_order" in text
    assert "position_order >= 0" in text
    assert "ck_job_source_assets_size_bytes" in text
    assert "size_bytes is null or size_bytes >= 0" in text


def test_migration_0046_does_not_fk_source_assets() -> None:
    text = _read_migration()
    # Strategy Option B: source_asset_id stays a historical reference (no FK to source_assets).
    assert "fk_job_source_assets_source_asset" not in text
    assert "historical" in text


def test_migration_0046_is_idempotent_guarded() -> None:
    text = _read_migration()
    assert text.count("if not exists") >= 4
    # Existing unique index from 0045 must not be re-created/altered here.
    assert "create unique nonclustered index uq_job_source_assets_job_asset_role" not in text
    assert "drop index uq_job_source_assets_job_asset_role" not in text
