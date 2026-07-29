"""Deterministic Python environment resolution for audit runners."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ResolvedPythonEnv:
    python_bin: str
    version: str
    venv_root: str | None
    selection_reason: str
    tools: dict[str, str | None]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _candidate_venvs(repo_root: Path) -> list[Path]:
    return [
        repo_root / "backend" / ".venv",
        repo_root / ".venv",
        repo_root / "venv",
        repo_root / "backend" / "venv",
    ]


def _python_in_venv(venv: Path) -> Path | None:
    for rel in ("bin/python", "bin/python3", "Scripts/python.exe", "Scripts/python3.exe"):
        candidate = venv / rel
        if candidate.is_file():
            return candidate
    return None


def _probe_version(python_bin: str) -> str:
    try:
        out = subprocess.check_output(
            [python_bin, "--version"],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=10,
        )
        return out.strip()
    except Exception as exc:  # noqa: BLE001 — diagnostic only
        return f"unknown ({exc})"


def _resolve_tool(python_bin: str, module: str, binary_name: str) -> str | None:
    """Prefer same-env binary, then `python -m module` availability."""
    py = Path(python_bin)
    sibling_dirs = [py.parent]
    # Windows Scripts vs Unix bin already covered by parent of python.
    for d in sibling_dirs:
        for name in (binary_name, f"{binary_name}.exe"):
            candidate = d / name
            if candidate.is_file():
                return str(candidate)
    # Module import check
    try:
        subprocess.check_call(
            [python_bin, "-c", f"import {module}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
        return f"{python_bin} -m {module}"
    except Exception:
        which = shutil.which(binary_name)
        return which


def resolve_python_env(repo_root: Path | None = None) -> ResolvedPythonEnv:
    """
    Resolution order:
    1. AUDIT_PYTHON / DINAMIC_AUDIT_PYTHON
    2. Known project virtualenvs
    3. VIRTUAL_ENV if set
    4. Current interpreter if it can import pytest
    5. sys.executable as last resort (may be incomplete)
    """
    root = (repo_root or Path(__file__).resolve().parents[3]).resolve()
    explicit = (os.environ.get("AUDIT_PYTHON") or os.environ.get("DINAMIC_AUDIT_PYTHON") or "").strip()
    if explicit:
        python_bin = explicit
        reason = "AUDIT_PYTHON / DINAMIC_AUDIT_PYTHON"
        venv_root = str(Path(python_bin).resolve().parent.parent)
    else:
        python_bin = ""
        reason = ""
        venv_root = None
        for venv in _candidate_venvs(root):
            py = _python_in_venv(venv)
            if py is not None:
                # Keep the venv path (do not follow symlinks to the base interpreter),
                # otherwise site-packages from the venv may be missed in diagnostics.
                python_bin = str(py)
                reason = f"project venv: {venv.relative_to(root) if venv.is_relative_to(root) else venv}"
                venv_root = str(venv)
                break
        if not python_bin:
            ve = (os.environ.get("VIRTUAL_ENV") or "").strip()
            if ve:
                py = _python_in_venv(Path(ve))
                if py is not None:
                    python_bin = str(py)
                    reason = "VIRTUAL_ENV"
                    venv_root = ve
        if not python_bin:
            # Prefer current interpreter if pytest is importable.
            try:
                import pytest  # noqa: F401

                python_bin = sys.executable
                reason = "current interpreter (pytest importable)"
            except Exception:
                python_bin = sys.executable
                reason = "current interpreter (fallback; tools may be missing)"

    tools = {
        "pytest": _resolve_tool(python_bin, "pytest", "pytest"),
        "ruff": _resolve_tool(python_bin, "ruff", "ruff"),
        "mypy": _resolve_tool(python_bin, "mypy", "mypy"),
        "bandit": _resolve_tool(python_bin, "bandit", "bandit"),
        "pip_audit": _resolve_tool(python_bin, "pip_audit", "pip-audit"),
    }
    return ResolvedPythonEnv(
        python_bin=python_bin,
        version=_probe_version(python_bin),
        venv_root=venv_root,
        selection_reason=reason,
        tools=tools,
    )


def write_python_env_report(path: Path, env: ResolvedPythonEnv | None = None) -> ResolvedPythonEnv:
    resolved = env or resolve_python_env()
    path.parent.mkdir(parents=True, exist_ok=True)
    import json

    path.write_text(json.dumps(resolved.to_dict(), indent=2) + "\n", encoding="utf-8")
    return resolved
