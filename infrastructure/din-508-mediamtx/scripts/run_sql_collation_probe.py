#!/usr/bin/env python3
"""Run readonly collation probe using repo root .env SQL settings."""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "backend"
SQL_FILE = Path(__file__).resolve().parent / "sql_aisle_code_collation_readonly.sql"
LITERAL_SQL = Path(__file__).resolve().parent / "sql_collation_literal_equivalence.sql"


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def main() -> int:
    load_dotenv(REPO_ROOT / ".env")
    if os.environ.get("SQLSERVER_ENABLED", "true").lower() not in ("1", "true", "yes"):
        print("SQLSERVER_ENABLED=false — skipping live SQL probe")
        return 0

    sys.path.insert(0, str(BACKEND_ROOT))
    from src.config import Settings  # noqa: PLC0415
    from src.database.sqlserver import SqlServerClient  # noqa: PLC0415

    settings = Settings()
    client = SqlServerClient(settings.require_sqlserver_connection_string())

    sql = SQL_FILE.read_text(encoding="utf-8") + "\n" + LITERAL_SQL.read_text(encoding="utf-8")
    statements = [s for s in sql.split(";") if s.strip() and not s.strip().startswith("--")]

    failures = 0
    with client.cursor() as cur:
        for stmt in statements:
            text = stmt.strip()
            if not text or text.upper().startswith("SET NOCOUNT"):
                try:
                    cur.execute(text)
                except Exception as exc:  # noqa: BLE001
                    print(f"-- FAILED: {text[:80]} ... {exc}")
                    failures += 1
                continue
            try:
                cur.execute(text)
            except Exception as exc:  # noqa: BLE001
                print(f"-- FAILED: {text.split(chr(10), 1)[0][:120]} ... {exc}")
                failures += 1
                continue
            if not cur.description:
                continue
            columns = [d[0] for d in cur.description]
            rows = cur.fetchall()
            print("--", text.split("\n", 1)[0][:120])
            print("|".join(columns))
            for row in rows:
                print("|".join("" if v is None else str(v) for v in row))
            print()
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 — POC diagnostic
        print(f"SQL probe failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc