"""Smoke test for the Phase 1 / Phase 7 v3 route → repository audit script."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_report_v3_route_repository_usage_exits_zero_with_expected_baseline() -> None:
    """Baseline: exactly one v3 route-level repo injection (aisles POST process). Update when that changes."""
    backend = Path(__file__).resolve().parents[2]
    script = backend / "scripts" / "report_v3_route_repository_usage.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(backend),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "aisles.py" in out
    assert "get_inventory_repo" in out
    assert "start_aisle_processing" in out
    assert "POST /{inventory_id}/aisles/{aisle_id}/process" in out
