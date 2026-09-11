"""Fail-closed Phase 5 flexible position preflight script checks."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PREFLIGHT = ROOT / "scripts" / "ops" / "phase-5-flexible-position-preflight.sql"
REVIEW_COPY = ROOT / "review" / "phase-5-flexible-position-preflight.sql"


def test_preflight_script_exists_and_throws_on_errors() -> None:
    text = PREFLIGHT.read_text(encoding="utf-8")
    # ``review/`` is gitignored; when a local review copy exists it must stay in sync.
    if REVIEW_COPY.exists():
        assert REVIEW_COPY.read_text(encoding="utf-8") == text
    assert "THROW 51011" in text
    assert "signature_policy" in text
    assert "position_flexible_capabilities" in text
    assert "UQ_pfc_scope_key" in text
    assert "UQ_aisle_locations_client_aisle_normalized_code_active" in text
    assert "ACTIVE_DUPLICATES" in text
    assert "position_materialization_requests" in text
    assert "position_materialization_association_receipts" in text
    assert "SET NOCOUNT OFF" in text
    assert "BAD_SIGNATURE_POLICY" in text
    assert "STATUS=''ACTIVE''" in text or "STATUS='ACTIVE'" in text


def test_validation_status_remains_honest() -> None:
    status = (ROOT / "scripts" / "ops" / "phase-5-flexible-position-validation.md").read_text(
        encoding="utf-8"
    )
    assert "PHASE_5_STATUS: IMPLEMENTED_WITH_BLOCKERS" in status
    assert "READY_FOR_CONTROLLED_ROLLOUT: NO" in status
    assert "GLOBAL_ROLLOUT: DISABLED" in status
