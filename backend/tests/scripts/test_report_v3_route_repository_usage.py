"""Smoke test for the Phase 1 / Phase 7 v3 route → repository audit script."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_report_v3_route_repository_usage_exits_zero_with_no_route_repo_injections() -> None:
    """Phase 9: v3 route handlers no longer use Depends(get_*_repo); script should report none."""
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
    assert (
        "(no Depends(get_*_repo) matches — v3 routes are clean at this layer.)" in out
    )
