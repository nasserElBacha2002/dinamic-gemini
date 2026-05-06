"""Unit tests for backend/scripts/patch_compose_host_port.py (CI-1.3.3 deploy helper)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

# Load module from backend/scripts (not under src) for direct unit tests
_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "patch_compose_host_port.py"
_spec = importlib.util.spec_from_file_location("patch_compose_host_port", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)
patch_compose_text = _mod.patch_compose_text
PATCH_FAILED_MSG = _mod.PATCH_FAILED_MSG


def test_patch_quoted_double() -> None:
    src = """services:
  api:
    ports:
      - "8000:8000"
"""
    out = patch_compose_text(src, "8001")
    assert '"8001:8000"' in out
    assert '"8000:8000"' not in out


def test_patch_quoted_single() -> None:
    src = """services:
  api:
    ports:
      - '8000:8000'
"""
    out = patch_compose_text(src, "8001")
    assert "'8001:8000'" in out


def test_patch_unquoted() -> None:
    src = """services:
  api:
    ports:
      - 8000:8000
"""
    out = patch_compose_text(src, "8001")
    assert "- 8001:8000" in out


def test_patch_explicit_host_ip() -> None:
    src = """services:
  api:
    ports:
      - "127.0.0.1:8000:8000"
"""
    out = patch_compose_text(src, "8001")
    assert '"127.0.0.1:8001:8000"' in out


def test_patch_negative_no_container_8000() -> None:
    src = """services:
  api:
    ports:
      - "9000:9000"
"""
    with pytest.raises(ValueError, match="Could not find any host"):
        patch_compose_text(src, "8001")


def test_idempotency_already_patched() -> None:
    src = """services:
  api:
    ports:
      - "8001:8000"
"""
    out = patch_compose_text(src, "8001")
    assert out == src
    assert '"8001:8000"' in out


def test_cli_on_temp_file(tmp_path: Path) -> None:
    """Smoke: script entrypoint mutates file and exits 0."""
    p = tmp_path / "docker-compose.yml"
    p.write_text(
        """services:
  api:
    ports:
      - "8000:8000"
""",
        encoding="utf-8",
    )
    r = subprocess.run(
        [sys.executable, str(_SCRIPT), "--compose", str(p), "--host-port", "8001"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    text = p.read_text(encoding="utf-8")
    assert '"8001:8000"' in text
