"""Migration 0064 presence checks."""

from __future__ import annotations

from pathlib import Path


def test_migration_0064_identity_and_lease() -> None:
    root = Path(__file__).resolve().parents[2]
    mig = (
        root
        / "src/database/migrations/versions/0064_preliminary_reconciliation_corrections.sql"
    )
    text = mig.read_text(encoding="utf-8")
    assert "UQ_pdr_preliminary_version_job" in text
    assert "lease_token" in text
    assert "next_retry_at" in text
    assert "row_version" in text
    assert "IX_pdr_worker_due" in text
