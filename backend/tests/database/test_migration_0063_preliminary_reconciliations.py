"""Migration 0063 presence / structure checks (no live SQL required)."""

from __future__ import annotations

from pathlib import Path


def test_migration_0063_creates_reconciliation_table() -> None:
    root = Path(__file__).resolve().parents[2]
    mig = (
        root
        / "src/database/migrations/versions/0063_preliminary_detection_reconciliations.sql"
    )
    text = mig.read_text(encoding="utf-8")
    assert "preliminary_detection_reconciliations" in text
    assert "UQ_pdr_preliminary_version" in text
    assert "NOT_COMPARABLE" in text
    assert "comparison_version" in text
    assert "Forward-only" in text or "forward-only" in text.lower()
