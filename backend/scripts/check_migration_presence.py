"""Fail CI when schema-affecting backend code changes without a migration SQL change.

This check is intentionally conservative about *which* code edits imply a DDL review, so that
persistence refactors and in-memory adapters do not demand a ``versions/*.sql`` artifact unless
canonical schema definitions or obvious SQL DDL edits are involved.

Examples that SHOULD require a ``backend/src/database/migrations/versions/*.sql`` change:
  - Any change to ``backend/src/database/schema.sql`` (canonical schema source).
  - Changes under ``backend/src/infrastructure/repositories/sql_*.py`` (or
    ``backend/src/database/repository.py``) whose **git diff** contains DDL-shaped SQL fragments.

Examples that SHOULD NOT require a migration:
  - ``backend/src/infrastructure/repositories/memory_*.py``
  - Refactors in ``sql_*.py`` that only touch queries/parameters/mapping without DDL tokens
  - ``backend/src/application/ports/repositories.py`` (contract-only; no automatic trigger)
  - Operational files listed in ignore prefixes (runner, docs, tests, etc.)
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Iterable

# Any change under this prefix whose path ends with ``.sql`` satisfies the migration requirement.
MIGRATION_SQL_PREFIX = "backend/src/database/migrations/versions/"

_REPO_PREFIX = "backend/src/infrastructure/repositories/"

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

# Strong DDL indicators only (case-insensitive). Intentionally excludes broad DML (SELECT/INSERT).
_DDL_PATTERN = re.compile(
    r"(?is)"
    r"\bCREATE\s+TABLE\b"
    r"|\bALTER\s+TABLE\b"
    r"|\bDROP\s+TABLE\b"
    r"|\bCREATE\s+(?:UNIQUE\s+)?INDEX\b"
    r"|\bDROP\s+INDEX\b"
    r"|\bADD\s+COLUMN\b"
    r"|\bDROP\s+COLUMN\b",
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


def _is_schema_definition_path(path: str) -> bool:
    """Files that are the canonical schema artifact; any edit requires a paired migration review."""
    return path == "backend/src/database/schema.sql"


def _is_memory_repository_path(path: str) -> bool:
    if not path.startswith(_REPO_PREFIX) or not path.endswith(".py"):
        return False
    filename = path.rsplit("/", 1)[-1]
    return filename.startswith("memory_")


def _is_sql_repository_path(path: str) -> bool:
    if not path.startswith(_REPO_PREFIX) or not path.endswith(".py"):
        return False
    filename = path.rsplit("/", 1)[-1]
    return filename.startswith("sql_")


def _is_database_repository_path(path: str) -> bool:
    return path == "backend/src/database/repository.py"


def _diff_text_looks_schema_affecting(diff_text: str) -> bool:
    """True when unified diff text (added/removed context lines) contains DDL-shaped SQL."""
    if not diff_text or not diff_text.strip():
        return False
    return _DDL_PATTERN.search(diff_text) is not None


def _git_changed_files(base_ref: str, head_ref: str) -> list[str]:
    proc = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...{head_ref}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _git_diff_for_path(base_ref: str, head_ref: str, path: str) -> str:
    proc = subprocess.run(
        ["git", "diff", f"{base_ref}...{head_ref}", "--", path],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout


def _path_requires_migration_review(path: str, base_ref: str, head_ref: str) -> bool:
    """
    Whether this changed path demands that ``versions/*.sql`` also changed.

    - ``schema.sql``: always (canonical DDL source of truth for humans).
    - Memory repos: never.
    - SQL repos / ``database/repository.py``: only when the diff contains DDL-shaped tokens.
    """
    if _is_schema_definition_path(path):
        return True
    if _is_memory_repository_path(path):
        return False
    if _is_sql_repository_path(path) or _is_database_repository_path(path):
        return _diff_text_looks_schema_affecting(_git_diff_for_path(base_ref, head_ref, path))
    return False


def _any_predicate(paths: Iterable[str], pred) -> bool:
    return any(pred(p) for p in paths)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate migration presence when schema-affecting code changes."
    )
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--head-ref", required=True)
    args = parser.parse_args()

    changed_files = _git_changed_files(args.base_ref, args.head_ref)
    if not changed_files:
        print("No changed files in range; migration check skipped.")
        return 0

    migration_sql_changed = _any_predicate(changed_files, _is_migration_sql)

    schema_sensitive_hits: list[str] = []
    for p in changed_files:
        if _is_ignored_path(p) or _is_migration_sql(p):
            continue
        if _path_requires_migration_review(p, args.base_ref, args.head_ref):
            schema_sensitive_hits.append(p)

    if not schema_sensitive_hits:
        print("No schema-affecting persistence changes detected; migration check skipped.")
        return 0
    if migration_sql_changed:
        print("Schema-affecting changes and migration SQL updates detected; check passed.")
        return 0

    print(
        "ERROR: Schema-affecting code changed but no migration file under versions/ was added/updated."
    )
    print(f"Expected at least one *.sql under: {MIGRATION_SQL_PREFIX}")
    print("Triggering files:")
    for path in schema_sensitive_hits:
        print(f" - {path}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
