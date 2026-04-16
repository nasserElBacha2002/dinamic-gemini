"""
Phase 12.5 — prevent accidental spread of ``src.database.repository`` imports outside the
legacy bridge (``job_store``) and the database package itself.

If this fails, either add the path to ``_ALLOWED_RELATIVE_PATHS`` with team review, or
remove the new import and use v3 persistence instead.
"""

from __future__ import annotations

import re
from pathlib import Path

_ALLOWED_RELATIVE_PATHS = frozenset(
    {
        "database/repository.py",
        "database/__init__.py",
        "jobs/job_store.py",
    }
)

_IMPORT_LINE = re.compile(
    r"^\s*(from\s+src\.database\.repository\s+import|import\s+src\.database\.repository)\b"
)


def test_src_tree_does_not_import_database_repository_outside_allowlist() -> None:
    backend = Path(__file__).resolve().parents[2]
    src_root = backend / "src"
    offenders: list[str] = []
    for path in sorted(src_root.rglob("*.py")):
        rel = path.relative_to(src_root).as_posix()
        if rel in _ALLOWED_RELATIVE_PATHS:
            continue
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if _IMPORT_LINE.match(line):
                offenders.append(f"{rel}:{lineno}:{stripped}")
    assert not offenders, "Unexpected legacy repository imports:\n" + "\n".join(offenders)
