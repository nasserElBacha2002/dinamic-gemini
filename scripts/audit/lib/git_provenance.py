"""Git provenance helpers for audit freshness checks."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Literal

WorkingTreeStatus = Literal["clean", "dirty", "unknown"]


def _run_git(repo_root: Path, *args: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        out = (proc.stdout or proc.stderr or "").strip()
        return proc.returncode, out
    except OSError as exc:
        return 127, str(exc)


def current_git_sha(repo_root: Path) -> str | None:
    rc, out = _run_git(repo_root, "rev-parse", "HEAD")
    if rc != 0 or not out:
        return None
    return out.splitlines()[0].strip()


def working_tree_status(repo_root: Path) -> WorkingTreeStatus:
    rc, out = _run_git(repo_root, "status", "--porcelain")
    if rc != 0:
        return "unknown"
    return "clean" if not out.strip() else "dirty"
