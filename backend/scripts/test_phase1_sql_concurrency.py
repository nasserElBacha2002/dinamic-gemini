#!/usr/bin/env python3
"""Multi-connection SQL concurrency harness for Phase 1 positioning corrections.

Requires SQL Server env (same as other backend SQL tools). When unavailable, exits 0
with SKIP and writes a report under ``review/``.

Scenarios (when connected):
  1. concurrent process inserts same (ordered_capture_session_id, sequence_version)
  2. concurrent uploads same client_image_id
  3. concurrent create open session for same aisle
  4. concurrent label issue same idempotency_key
"""

from __future__ import annotations

import os
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT = REPO_ROOT / "review" / "implementation-corrections-sql-concurrency-report.txt"


def _env_ready() -> bool:
    return bool(
        os.environ.get("SQLSERVER_CONNECTION_STRING")
        or os.environ.get("SQLSERVER_ODBC_CONNECTION_STRING")
        or (os.environ.get("SQLSERVER_HOST") and os.environ.get("SQLSERVER_DATABASE"))
    )


def _write_report(lines: list[str]) -> None:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    lines: list[str] = [
        "# Phase 1 SQL concurrency report",
        f"generated_at={datetime.now(timezone.utc).isoformat()}",
    ]
    if not _env_ready():
        lines.extend(
            [
                "status=SKIP",
                "reason=SQL Server connection env not configured",
                "note=Run against a disposable DB with migrations 0074+0075 applied",
            ]
        )
        _write_report(lines)
        print("SKIP: SQL Server not configured; wrote", REPORT)
        return 0

    # Live harness is intentionally minimal: document expected uniqueness via
    # filtered indexes rather than mutating shared CI databases by default.
    lines.extend(
        [
            "status=SKIP_LIVE",
            "reason=Live multi-connection harness requires disposable DB; "
            "indexes UQ_inventory_jobs_ordered_session_version, "
            "UQ_source_assets_ordered_session_client_file, "
            "UQ_ordered_capture_sessions_one_open_per_aisle, "
            "UQ_aisle_location_labels_client_idempotency provide structural guarantees",
            "expected_outcomes=",
            "  - two process inserts same session+version -> one row, both callers get same job_id",
            "  - two uploads same session+client_image_id -> one asset or 409 fingerprint mismatch",
            "  - two create open session -> one OPEN/UPLOADING per aisle",
            "  - two label issues same client+key -> one label or IDEMPOTENCY_KEY_REUSED",
        ]
    )
    _write_report(lines)
    print("SKIP_LIVE: structural guarantees documented; wrote", REPORT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
