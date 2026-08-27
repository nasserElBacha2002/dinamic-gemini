#!/usr/bin/env python3
"""Fold migration DDL into ``schema.sql`` so clean installs match the latest schema version.

Canonical workflow for a new database:
  1. Apply ``backend/src/database/schema.sql`` (bootstrap + folded migrations).
  2. Run ``db_migrate apply`` (records version markers; DDL is idempotent no-ops).

Re-run this script after adding migrations that introduce tables/columns/constraints
not yet represented in ``schema.sql``:

  python backend/scripts/fold_migrations_into_schema.py
  python backend/scripts/fold_migrations_into_schema.py --check   # exit 2 if drift
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "backend/src/database/schema.sql"
VERSIONS = REPO_ROOT / "backend/src/database/migrations/versions"

MARKER_BEGIN = "-- >>> FOLDED_FROM_MIGRATIONS_BEGIN (auto; keep schema.sql aligned with migrations/versions)"
MARKER_END = "-- <<< FOLDED_FROM_MIGRATIONS_END"

# Created in early migrations then dropped (0029); must not appear in bootstrap.
SKIP_TABLES = frozenset({"inventory_visual_references"})

# Constraint/index-only migrations that column heuristics may skip.
EXTRA_NAMED_OBJECT_MIGRATIONS = frozenset(
    {
        "0034_aisle_code_scan_constraints.sql",
        "0036_code_scan_matching_constraints.sql",
        "0044_source_assets_upload_idempotency.sql",
        "0047_position_creation_source_and_manual_coverage.sql",
        "0060_asset_processing_commands.sql",
        "0073_inventory_jobs_retry_of_unique.sql",
        "0081_image_position_label_detections_job_scope.sql",
        "0083_position_reconciliation_hardening.sql",
        "0085_ipld_legacy_unsigned_detection_status.sql",
        "0089_product_label_identity_hardening.sql",
        "0092_client_position_label_active_marker_unique.sql",
        "0094_local_csv_multi_product_secondary.sql",
    }
)

CREATE_RE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:\[?dbo\]?\.)?\[?(\w+)\]?",
    re.I,
)
ADD_COL_RE = re.compile(
    r"ALTER\s+TABLE\s+(?:\[?dbo\]?\.)?\[?(\w+)\]?\s+ADD(?!\s+CONSTRAINT)(?:\s+COLUMN)?\s+\[?(\w+)\]?",
    re.I,
)
COL_LENGTH_RE = re.compile(
    r"COL_LENGTH\(\s*'(\w+)'\s*,\s*'(\w+)'\s*\)|"
    r"object_id\s*=\s*OBJECT_ID\(\s*(?:N)?'(?:dbo\.)?(\w+)'\s*\)\s+AND\s+name\s*=\s*(?:N)?'(\w+)'",
    re.I,
)
CONSTRAINT_RE = re.compile(r"ADD\s+CONSTRAINT\s+\[?(\w+)\]?", re.I)
INDEX_RE = re.compile(r"CREATE\s+(?:UNIQUE\s+)?(?:NONCLUSTERED\s+)?INDEX\s+\[?(\w+)\]?", re.I)
NAMED_OBJ_RE = re.compile(r"name\s*=\s*(?:N)?'(\w+)'", re.I)


def migration_sort_key(name: str) -> tuple:
    m = re.match(r"^(\d+)([a-z]?)", name)
    if not m:
        return (9999, "", name)
    return (int(m.group(1)), m.group(2) or "", name)


def list_ups() -> list[Path]:
    files = [
        p
        for p in VERSIONS.glob("*.sql")
        if not p.name.endswith(".down.sql") and re.match(r"^\d+", p.name)
    ]
    return sorted(files, key=lambda p: migration_sort_key(p.name))


def tables_in_sql(text: str) -> set[str]:
    return {t.lower() for t in CREATE_RE.findall(text)}


def columns_referenced_as_present(text: str) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    skip_tokens = {
        "constraint",
        "primary",
        "foreign",
        "unique",
        "check",
        "default",
        "not",
        "null",
        "column",
    }
    for table, col in ADD_COL_RE.findall(text):
        if col.lower() in skip_tokens:
            continue
        found.add((table.lower(), col.lower()))
    for m in COL_LENGTH_RE.finditer(text):
        if m.group(1) and m.group(2):
            found.add((m.group(1).lower(), m.group(2).lower()))
        elif m.group(3) and m.group(4):
            found.add((m.group(3).lower(), m.group(4).lower()))
    for m in re.finditer(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:\[?dbo\]?\.)?\[?(\w+)\]?\s*\((.*?)\)\s*;",
        text,
        flags=re.I | re.S,
    ):
        table = m.group(1).lower()
        for line in m.group(2).splitlines():
            line = line.strip().rstrip(",")
            if not line or line.upper().startswith(
                ("CONSTRAINT", "PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "INDEX")
            ):
                continue
            cm = re.match(r"\[?(\w+)\]?\s+", line)
            if cm and cm.group(1).upper() not in {
                "CONSTRAINT",
                "PRIMARY",
                "FOREIGN",
                "UNIQUE",
                "CHECK",
            }:
                found.add((table, cm.group(1).lower()))
    return found


def migration_effects(text: str) -> tuple[set[str], set[tuple[str, str]]]:
    creates = tables_in_sql(text)
    cols: set[tuple[str, str]] = set()
    skip_tokens = {
        "constraint",
        "primary",
        "foreign",
        "unique",
        "check",
        "default",
        "not",
        "null",
        "column",
    }
    for table, col in ADD_COL_RE.findall(text):
        if col.lower() in skip_tokens:
            continue
        cols.add((table.lower(), col.lower()))
    for m in COL_LENGTH_RE.finditer(text):
        if m.group(1) and m.group(2):
            cols.add((m.group(1).lower(), m.group(2).lower()))
        elif m.group(3) and m.group(4):
            cols.add((m.group(3).lower(), m.group(4).lower()))
    return creates, cols


def named_objects(text: str) -> set[str]:
    objs = set(CONSTRAINT_RE.findall(text)) | set(INDEX_RE.findall(text))
    objs |= {
        n
        for n in NAMED_OBJ_RE.findall(text)
        if re.match(r"^(CK_|IX_|UQ_|PK_|DF_|UX_)", n)
    }
    return objs


def strip_existing_fold(schema: str) -> str:
    """Remove any folded section, tolerant of marker comment text changes."""
    pattern = re.compile(
        r"\n*-- >>> FOLDED_FROM_MIGRATIONS_BEGIN.*?\n-- <<< FOLDED_FROM_MIGRATIONS_END\n*",
        re.S,
    )
    return pattern.sub("\n", schema).rstrip() + "\n"


def compute_migrations_to_fold(schema_base: str) -> list[str]:
    schema_tables = tables_in_sql(schema_base)
    schema_cols = columns_referenced_as_present(schema_base)
    effective_tables = set(schema_tables)
    effective_cols = set(schema_cols)
    to_fold: list[str] = []

    for path in list_ups():
        text = path.read_text(errors="ignore")
        creates, cols = migration_effects(text)
        creates = {t for t in creates if t not in SKIP_TABLES}
        need = any(t not in effective_tables for t in creates)
        if not need:
            for table, col in cols:
                if (table in creates or table in effective_tables) and (
                    table,
                    col,
                ) not in effective_cols:
                    need = True
                    break
        if not need and path.name in EXTRA_NAMED_OBJECT_MIGRATIONS:
            missing_named = [o for o in named_objects(text) if o not in schema_base]
            # Also compare against previously folded names in this pass via effective content
            if missing_named:
                # If objects appear later in folded set we rebuild wholesale — mark need when
                # not present in base schema text.
                need = True
        if need:
            to_fold.append(path.name)
            effective_tables |= creates
            effective_cols |= cols
            effective_cols |= columns_referenced_as_present(text)

    # Ensure EXTRA migrations are included when their named objects are absent from base
    # (after first pass some EXTRAs may still be needed relative to base-only schema).
    folded = set(to_fold)
    for name in sorted(EXTRA_NAMED_OBJECT_MIGRATIONS, key=migration_sort_key):
        if name in folded:
            continue
        text = (VERSIONS / name).read_text(errors="ignore")
        if any(o not in schema_base for o in named_objects(text)):
            folded.add(name)
    return sorted(folded, key=migration_sort_key)


def build_fold_section(migration_names: list[str]) -> str:
    parts = [
        MARKER_BEGIN,
        "-- Idempotent DDL copied from migrations/versions so clean installs match latest schema.",
        "-- Safe alongside db_migrate apply (IF NOT EXISTS / COL_LENGTH guards).",
        "-- Prefer: update the migration, then re-run this script.",
        "",
    ]
    for name in migration_names:
        parts.append(f"-- ----- folded from {name} -----")
        parts.append((VERSIONS / name).read_text(errors="ignore").rstrip())
        parts.append("GO")
        parts.append("")
    parts.append(MARKER_END)
    parts.append("")
    return "\n".join(parts)


def verify(schema_text: str) -> tuple[list[str], list[str]]:
    schema_tables = tables_in_sql(schema_text)
    schema_cols = columns_referenced_as_present(schema_text)
    mig_tables: set[str] = set()
    mig_cols: set[tuple[str, str]] = set()
    missing_named: list[str] = []
    for path in list_ups():
        text = path.read_text(errors="ignore")
        creates, cols = migration_effects(text)
        mig_tables |= {t for t in creates if t not in SKIP_TABLES}
        mig_cols |= cols
        if path.name in EXTRA_NAMED_OBJECT_MIGRATIONS or path.name in re.findall(
            r"folded from (\S+\.sql)", schema_text
        ):
            for obj in named_objects(text):
                if obj not in schema_text:
                    missing_named.append(f"{path.name}:{obj}")
    missing_t = sorted(mig_tables - schema_tables)
    missing_c = sorted(
        f"{t}.{c}"
        for t, c in mig_cols
        if t not in SKIP_TABLES and (t, c) not in schema_cols and t in (mig_tables | schema_tables)
    )
    return missing_t + [f"col:{c}" for c in missing_c], missing_named


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write; exit 2 if schema.sql drifts from migrations.",
    )
    args = parser.parse_args()

    schema_raw = SCHEMA_PATH.read_text()
    schema_base = strip_existing_fold(schema_raw)
    to_fold = compute_migrations_to_fold(schema_base)
    # When checking an already-folded file, verify against full text
    if args.check:
        missing_core, missing_named = verify(schema_raw)
        if missing_core or missing_named:
            print("DRIFT detected:")
            for m in missing_core:
                print(f"  - {m}")
            for m in missing_named:
                print(f"  - named {m}")
            return 2
        folded_n = len(re.findall(r"folded from \S+\.sql", schema_raw))
        print(
            f"OK: schema.sql aligned with migrations "
            f"(CREATE TABLE={len(tables_in_sql(schema_raw))}, folded={folded_n})."
        )
        return 0

    new_schema = schema_base.rstrip() + "\n\n" + build_fold_section(to_fold)
    SCHEMA_PATH.write_text(new_schema)
    missing_core, missing_named = verify(new_schema)
    print(f"Wrote {SCHEMA_PATH.relative_to(REPO_ROOT)} ({len(new_schema.splitlines())} lines)")
    print(f"Folded {len(to_fold)} migrations.")
    if missing_core or missing_named:
        print("WARNING: residual gaps after fold:")
        for m in missing_core + missing_named:
            print(f"  - {m}")
        return 2
    print("Verification OK: no missing tables/columns/named objects.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
