"""Fail CI when DB-layer code changes without a new migration file."""

from __future__ import annotations

import argparse
import subprocess
import sys
from typing import List


DB_TOUCH_PATH_PREFIXES = (
    "backend/src/database/",
    "backend/src/infrastructure/",
    "backend/src/application/",
)

MIGRATION_PREFIX = "backend/src/database/migrations/versions/"


def _git_changed_files(base_ref: str, head_ref: str) -> List[str]:
    proc = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...{head_ref}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate migration presence when DB code changes.")
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--head-ref", required=True)
    args = parser.parse_args()

    changed_files = _git_changed_files(args.base_ref, args.head_ref)
    touched_db_code = any(path.startswith(DB_TOUCH_PATH_PREFIXES) for path in changed_files)
    touched_migration = any(path.startswith(MIGRATION_PREFIX) and path.endswith(".sql") for path in changed_files)

    if not touched_db_code:
        print("No DB-related code changes detected; migration check skipped.")
        return 0
    if touched_migration:
        print("DB-related code and migration file changes detected; check passed.")
        return 0

    print("ERROR: DB-related code changed but no migration file was added/updated.")
    print(f"Expected at least one *.sql under: {MIGRATION_PREFIX}")
    for path in changed_files:
        print(f" - {path}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
