"""Fail CI when schema-affecting backend code changes without a migration SQL change.

This check is intentionally narrow: operational noise (migration runner, docs, workflows)
must not force a new *.sql migration.

Examples that SHOULD require a ``backend/src/database/migrations/versions/*.sql`` change:
  - backend/src/database/schema.sql
  - backend/src/database/repository.py
  - backend/src/infrastructure/repositories/sql_foo_repository.py (SQL / table access)
  - backend/src/application/ports/repositories.py (persistence contract changes)

Examples that SHOULD NOT require a migration:
  - backend/src/database/migrations/*.py (runner, cli, service bookkeeping)
  - backend/scripts/db_migrate.py, backend/scripts/check_migration_presence.py
  - docs/** , backend/README.md , .github/workflows/**
  - backend/pyproject.toml (packaging only)
  - backend/src/api/** (HTTP layer without persistence changes)
  - backend/src/infrastructure/pipeline/** (no SQL DDL/DML to app schema)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from typing import Iterable, List

# Any change under this prefix whose path ends with ``.sql`` satisfies the migration requirement.
MIGRATION_SQL_PREFIX = "backend/src/database/migrations/versions/"

# Paths that never count as “schema-affecting” (operational / docs / runner noise).
_IGNORE_PREFIXES: tuple[str, ...] = (
    "docs/",
    ".github/workflows/",
    "backend/scripts/",
    "backend/tests/",
)

_IGNORE_EXACT: frozenset[str] = frozenset(
    {
        "backend/README.md",
        "backend/pyproject.toml",
    }
)


def _is_migration_sql(path: str) -> bool:
    return path.startswith(MIGRATION_SQL_PREFIX) and path.endswith(".sql")


def _is_ignored_path(path: str) -> bool:
    if path in _IGNORE_EXACT:
        return True
    # Under migrations/: only ``versions/*.sql`` matters; all other files (``.py``, etc.) ignored.
    if path.startswith("backend/src/database/migrations/"):
        return not _is_migration_sql(path)
    return any(path.startswith(p) for p in _IGNORE_PREFIXES)


def _is_schema_sensitive_path(path: str) -> bool:
    """True when the change likely needs a DDL/DML migration reviewed by a human."""
    if path.startswith("backend/src/infrastructure/repositories/") and path.endswith(".py"):
        return True
    if path == "backend/src/database/schema.sql":
        return True
    if path == "backend/src/database/repository.py":
        return True
    if path == "backend/src/application/ports/repositories.py":
        return True
    return False


def _git_changed_files(base_ref: str, head_ref: str) -> List[str]:
    proc = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...{head_ref}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _any_predicate(paths: Iterable[str], pred) -> bool:
    return any(pred(p) for p in paths)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate migration presence when schema-affecting code changes.")
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--head-ref", required=True)
    args = parser.parse_args()

    changed_files = _git_changed_files(args.base_ref, args.head_ref)
    if not changed_files:
        print("No changed files in range; migration check skipped.")
        return 0

    migration_sql_changed = _any_predicate(changed_files, _is_migration_sql)

    # Only files that are neither ignored nor “the migration SQL itself” can trigger the requirement.
    schema_sensitive_hits = [
        p
        for p in changed_files
        if not _is_ignored_path(p) and not _is_migration_sql(p) and _is_schema_sensitive_path(p)
    ]

    if not schema_sensitive_hits:
        print("No schema-affecting persistence changes detected; migration check skipped.")
        return 0
    if migration_sql_changed:
        print("Schema-affecting changes and migration SQL updates detected; check passed.")
        return 0

    print("ERROR: Schema-affecting code changed but no migration file under versions/ was added/updated.")
    print(f"Expected at least one *.sql under: {MIGRATION_SQL_PREFIX}")
    print("Triggering files:")
    for path in schema_sensitive_hits:
        print(f" - {path}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
