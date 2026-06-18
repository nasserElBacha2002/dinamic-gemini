"""Phase 4.6 — migration 0042 result_evidence table."""

from __future__ import annotations

from pathlib import Path


def test_migration_0042_exists_and_defines_result_evidence() -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "src/database/migrations/versions/0042_result_evidence_structural_persistence.sql"
    )
    text = path.read_text(encoding="utf-8")
    assert "CREATE TABLE result_evidence" in text
    assert "IX_result_evidence_job_id" in text
    assert "has_valid_evidence" in text
    assert "traceability_status" in text
