"""Phase 7 — reconcile_aisle deprecation must be visible on stderr."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_reconcile_aisle_prints_deprecation_on_stderr() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    proc = subprocess.run(
        [sys.executable, "-c", "import scripts.ops.reconcile_aisle"],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert "DEPRECATED" in proc.stderr
    assert "inspect_aisle" in proc.stderr
    assert "2026-12-31" in proc.stderr
    assert "PHASE7-CLEANUP-RECONCILE-AISLE" in proc.stderr
    assert proc.returncode == 0


def test_reconcile_aisle_module_source_documents_sunset() -> None:
    mod_path = Path(__file__).resolve().parents[3] / "scripts" / "ops" / "reconcile_aisle.py"
    text = mod_path.read_text(encoding="utf-8")
    assert "2026-12-31" in text
    assert "sys.stderr" in text
    assert "warnings.warn" not in text
    assert "PHASE7-CLEANUP-RECONCILE-AISLE" in text
