"""Helpers for safe aggregate audit artifact lifecycle."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


AGGREGATE_STATUS_NAME = "audit-status.json"
AGGREGATE_SUMMARY_NAME = "audit-summary.md"


def clear_aggregate_outputs(audit_dir: Path) -> None:
    """Remove published aggregate outputs so the gate cannot consume stale data."""
    for name in (AGGREGATE_STATUS_NAME, AGGREGATE_SUMMARY_NAME):
        path = audit_dir / name
        if path.exists():
            path.unlink()


def publish_aggregate_outputs(
    *,
    audit_dir: Path,
    status_tmp: Path,
    summary_tmp: Path,
) -> None:
    """Atomically replace published aggregates only after successful generation."""
    audit_dir.mkdir(parents=True, exist_ok=True)
    status_dest = audit_dir / AGGREGATE_STATUS_NAME
    summary_dest = audit_dir / AGGREGATE_SUMMARY_NAME
    # Replace on same filesystem via os.replace for atomicity.
    os.replace(status_tmp, status_dest)
    os.replace(summary_tmp, summary_dest)


def write_run_marker(raw_dir: Path, run_id: str) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "LATEST_RUN.txt").write_text(f"{run_id}\n", encoding="utf-8")


def snapshot_raw_outputs(raw_dir: Path, run_id: str) -> Path:
    """Copy flat raw files into raw/runs/<run_id>/ (last snapshot only)."""
    runs_dir = raw_dir / "runs"
    if runs_dir.exists():
        shutil.rmtree(runs_dir)
    arch = runs_dir / run_id
    arch.mkdir(parents=True, exist_ok=True)
    for f in raw_dir.iterdir():
        if not f.is_file():
            continue
        if f.name in {".gitkeep", "LATEST_RUN.txt"}:
            continue
        shutil.copy2(f, arch / f.name)
    write_run_marker(raw_dir, run_id)
    return arch
