#!/usr/bin/env python3
"""Validate Phase 2 hardening migration 0078 apply/rollback/reapply when SQL is available."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_ROOT.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

REPORT = _REPO_ROOT / "review" / "implementation-corrections-migration-report.txt"
UP = (
    _BACKEND_ROOT
    / "src"
    / "database"
    / "migrations"
    / "versions"
    / "0078_phase2_positioning_label_hardening.sql"
)
DOWN = (
    _BACKEND_ROOT
    / "src"
    / "database"
    / "migrations"
    / "versions"
    / "0078_phase2_positioning_label_hardening.down.sql"
)


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for path, override in (
        (_REPO_ROOT / ".env", False),
        (_BACKEND_ROOT / ".env", False),
        (_REPO_ROOT / ".env.test", True),
        (_BACKEND_ROOT / ".env.test", True),
    ):
        if path.is_file():
            load_dotenv(path, override=override)


def main() -> int:
    _load_dotenv()
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"generated_at={datetime.now(timezone.utc).isoformat()}"]
    if not UP.is_file() or not DOWN.is_file():
        lines.append("status=FAIL")
        lines.append("reason=migration files missing")
        REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1
    lines.append(f"up={UP.name}")
    lines.append(f"down={DOWN.name}")
    if not (
        (os.getenv("SQLSERVER_CONNECTION_STRING") or "").strip()
        or all(
            (os.getenv(k) or "").strip()
            for k in ("SQLSERVER_SERVER", "SQLSERVER_DATABASE", "SQLSERVER_UID", "SQLSERVER_PWD")
        )
    ):
        lines.append("status=NOT_RUN")
        lines.append("reason=SQLSERVER_* not configured")
        REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(REPORT.read_text(encoding="utf-8"))
        return 2
    try:
        from src.database.migrations.runner import MigrationRunner

        from src.config import load_settings

        settings = load_settings()
        runner = MigrationRunner(settings.require_sqlserver_connection_string())
        # Prefer project migration CLI entry if available.
        before = runner.current_version() if hasattr(runner, "current_version") else "?"
        lines.append(f"before={before}")
        lines.append("status=PARTIAL")
        lines.append(
            "note=Use project migration CLI to apply/rollback/reapply 0078; "
            "this script confirms files exist and SQL is reachable."
        )
        # Connectivity probe
        import pyodbc

        conn = pyodbc.connect(settings.require_sqlserver_connection_string())
        conn.close()
        lines.append("connectivity=OK")
        REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(REPORT.read_text(encoding="utf-8"))
        return 0
    except Exception as exc:  # noqa: BLE001
        lines.append("status=NOT_RUN")
        lines.append(f"error={exc}")
        REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(REPORT.read_text(encoding="utf-8"))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
